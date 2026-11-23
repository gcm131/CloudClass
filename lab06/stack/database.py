"""Create and delete the private, encrypted, single-AZ PostgreSQL RDS instance."""
from __future__ import annotations
import logging
import secrets
import time
from botocore.exceptions import ClientError
from . import network
from .clients import AwsClients
from .config import Settings
from .outputs import DbOutputs
from .util import error_code, ignore_errors

log = logging.getLogger("stack")

def ensure_db_subnet_group(aws: AwsClients, settings: Settings, subnets: list[str]) -> None:
    """Create the DB subnet group spanning two AZs."""
    with ignore_errors("DBSubnetGroupAlreadyExists"):
        aws.rds.create_db_subnet_group(
            DBSubnetGroupName=settings.db_subnet_group_name,
            DBSubnetGroupDescription="Lab subnets for the weather database",
            SubnetIds=subnets,
        )
        log.info("Created DB subnet group %s", settings.db_subnet_group_name)

def ensure_db_password(aws: AwsClients, param_name: str) -> str:
    """Return existing password from SSM or generate a new 32-char hex password."""
    try:
        out = aws.ssm.get_parameter(Name=param_name, WithDecryption=True)
        return out["Parameter"]["Value"]
    except ClientError as err:
        if error_code(err) != "ParameterNotFound":
            raise
    password = secrets.token_hex(16)
    aws.ssm.put_parameter(Name=param_name, Type="SecureString", Value=password, Overwrite=True)
    log.info("Generated and stored new DB password parameter %s", param_name)
    return password

def db_instance_exists(aws: AwsClients, db_id: str) -> bool:
    try:
        aws.rds.describe_db_instances(DBInstanceIdentifier=db_id)
        return True
    except ClientError as err:
        if error_code(err) != "DBInstanceNotFound":
            raise
        return False

def create_database(settings: Settings, aws: AwsClients, wait: bool = True) -> DbOutputs:
    """Create DB SG, subnet group, SSM password, and free-tier PostgreSQL RDS instance."""
    vpc_id = network.default_vpc_id(aws)
    subnet_a = network.subnet_in_az(aws, vpc_id, settings.az_a)
    subnet_b = network.subnet_in_az(aws, vpc_id, settings.az_b)
    db_sg_id = network.ensure_db_security_group(aws, settings, vpc_id)
    ensure_db_subnet_group(aws, settings, [subnet_a, subnet_b])

    password = ensure_db_password(aws, settings.db_password_param)
    if not db_instance_exists(aws, settings.db_instance_id):
        aws.rds.create_db_instance(
            DBInstanceIdentifier=settings.db_instance_id,
            DBInstanceClass="db.t4g.micro",
            Engine="postgres",
            AllocatedStorage=20,
            StorageType="gp2",
            MasterUsername=settings.db_user,
            MasterUserPassword=password,
            DBName=settings.db_name,
            DBSubnetGroupName=settings.db_subnet_group_name,
            VpcSecurityGroupIds=[db_sg_id],
            AvailabilityZone=settings.az_a,
            BackupRetentionPeriod=0,
            MultiAZ=False,
            PubliclyAccessible=False,
            AutoMinorVersionUpgrade=False,
            DeletionProtection=False,
            StorageEncrypted=True,
        )
        log.info("Creating RDS instance %s (takes 5 to 10 minutes)...", settings.db_instance_id)
    else:
        log.info("Database %s already exists, skipping creation.", settings.db_instance_id)
    del password

    if wait:
        aws.rds.get_waiter("db_instance_available").wait(DBInstanceIdentifier=settings.db_instance_id)

    instances = aws.rds.describe_db_instances(DBInstanceIdentifier=settings.db_instance_id)["DBInstances"]
    endpoint = instances[0].get("Endpoint", {}).get("Address", "pending")
    return DbOutputs(db_host=endpoint, db_security_group_id=db_sg_id)

def delete_database(settings: Settings, aws: AwsClients, wait: bool = True, sleep=time.sleep) -> None:
    """Delete RDS instance with no final snapshot or retained backups, plus SG, subnet group, and SSM secret."""
    if db_instance_exists(aws, settings.db_instance_id):
        with ignore_errors("InvalidDBInstanceState"):
            aws.rds.delete_db_instance(
                DBInstanceIdentifier=settings.db_instance_id,
                SkipFinalSnapshot=True,
                DeleteAutomatedBackups=True,
            )
            log.info("Deleting RDS instance %s...", settings.db_instance_id)
        if wait:
            aws.rds.get_waiter("db_instance_deleted").wait(DBInstanceIdentifier=settings.db_instance_id)
    else:
        log.info("Database %s not found, skipping.", settings.db_instance_id)

    with ignore_errors("DBSubnetGroupNotFoundFault"):
        aws.rds.delete_db_subnet_group(DBSubnetGroupName=settings.db_subnet_group_name)
        log.info("Deleted DB subnet group %s", settings.db_subnet_group_name)

    vpc_id = network.default_vpc_id(aws)
    db_sg_id = network.find_security_group(aws, settings.db_sg_name, vpc_id)
    if db_sg_id:
        network.delete_security_group_with_retry(aws, db_sg_id, sleep=sleep)

    with ignore_errors("ParameterNotFound"):
        aws.ssm.delete_parameter(Name=settings.db_password_param)
        log.info("Deleted parameter %s", settings.db_password_param)

    DbOutputs.remove()