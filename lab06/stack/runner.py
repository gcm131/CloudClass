"""Build and tear down the two-tier Weather Advisor stack."""
from __future__ import annotations
import logging
import time
from botocore.exceptions import ClientError
from . import balancer, compute, iam, network, scaling
from .clients import AwsClients
from .config import Settings
from .outputs import DbOutputs, StackOutputs
from .util import error_code

log = logging.getLogger("stack")

def check_prerequisites(settings: Settings, aws: AwsClients, db_outputs: DbOutputs | None = None) -> DbOutputs:
    """Verify the Gemini key exists in SSM and the database outputs are available."""
    try:
        aws.ssm.get_parameter(Name=settings.gemini_param_name)
    except ClientError as err:
        if error_code(err) == "ParameterNotFound":
            raise network.StackError(
                f"Parameter {settings.gemini_param_name} was not found. Store it first (Part C)."
            ) from err
        raise

    if db_outputs is not None:
        return db_outputs
    try:
        return DbOutputs.load()
    except FileNotFoundError as err:
        raise network.StackError(
            "db_outputs.json was not found. Run python3 create_database.py first (Part E)."
        ) from err

def create_weather_stack(
    settings: Settings,
    aws: AwsClients,
    db_outputs: DbOutputs | None = None,
    iam_wait: int = 15,
    sleep=time.sleep,
) -> StackOutputs:
    db = check_prerequisites(settings, aws, db_outputs=db_outputs)
    account_id = aws.sts.get_caller_identity()["Account"]

    log.info("== IAM roles and instance profiles ==")
    for tier in settings.tiers:
        iam.ensure_role_and_profile(aws, settings, tier, account_id)
    log.info("Waiting %ss for IAM propagation...", iam_wait)
    sleep(iam_wait)

    log.info("== Network ==")
    vpc_id = network.default_vpc_id(aws)
    subnet_a = network.subnet_in_az(aws, vpc_id, settings.az_a)
    subnet_b = network.subnet_in_az(aws, vpc_id, settings.az_b)
    alb_sg_id = network.ensure_alb_security_group(aws, settings, vpc_id)
    network.restrict_app_security_group(aws, settings, alb_sg_id)

    log.info("== Target groups, load balancer, listeners (ALB before Launch Templates) ==")
    tg_arns = {
        tier.name: balancer.ensure_target_group(aws, settings, tier, vpc_id)
        for tier in settings.tiers
    }
    alb_arn, alb_dns = balancer.ensure_load_balancer(aws, settings, [subnet_a, subnet_b], alb_sg_id)
    for tier in settings.tiers:
        balancer.ensure_listener(aws, alb_arn, tier.listener_port, tg_arns[tier.name])

    log.info("== Launch templates ==")
    for tier in settings.tiers:
        compute.ensure_launch_template(
            aws, settings, tier, alb_dns_name=alb_dns, db_host=db.db_host
        )

    log.info("== Auto Scaling Groups ==")
    for tier in settings.tiers:
        scaling.ensure_asg(aws, tier, tg_arns[tier.name], [subnet_a, subnet_b])

    return StackOutputs(
        vpc_id=vpc_id, subnet_a=subnet_a, subnet_b=subnet_b,
        alb_security_group_id=alb_sg_id, alb_arn=alb_arn, alb_dns_name=alb_dns,
        weather_tg_arn=tg_arns["weather"], advisor_tg_arn=tg_arns["advisor"],
    )

def delete_weather_stack(settings: Settings, aws: AwsClients, sleep=time.sleep) -> None:
    """Tear down ASGs, ALB, target groups, ALB SG, launch templates, and IAM roles."""
    log.info("== Auto Scaling Groups ==")
    for tier in settings.tiers:
        scaling.delete_asg(aws, tier.asg_name, sleep=sleep)

    log.info("== Load balancer and target groups ==")
    balancer.delete_load_balancer(aws, settings.alb_name)
    for tier in settings.tiers:
        balancer.delete_target_group(aws, tier.tg_name)

    log.info("== Security groups ==")
    vpc_id = network.default_vpc_id(aws)
    alb_sg_id = network.find_security_group(aws, settings.alb_sg_name, vpc_id)
    network.restore_app_security_group(aws, settings, alb_sg_id)
    if alb_sg_id:
        network.delete_security_group_with_retry(aws, alb_sg_id, sleep=sleep)

    log.info("== Launch templates and IAM ==")
    for tier in settings.tiers:
        compute.delete_launch_template(aws, tier)
        iam.delete_role_and_profile(aws, tier)

    StackOutputs.remove()
    log.info("Weather stack removed.")