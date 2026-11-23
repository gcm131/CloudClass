"""Integration and chaos tests against the live Weather Advisor stack."""
import subprocess
import time
import pytest
import requests
from tests.helpers import get_json, tcp_open, wait_until

def _decision(aws, role_name: str, action: str, resource: str) -> str:
    role_arn = aws.iam.get_role(RoleName=role_name)["Role"]["Arn"]
    res = aws.iam.simulate_principal_policy(
        PolicySourceArn=role_arn, ActionNames=[action], ResourceArns=[resource]
    )
    return res["EvaluationResults"][0]["EvalDecision"]

def _running_instance(aws, tag_name: str) -> dict:
    resp = aws.ec2.describe_instances(Filters=[
        {"Name": "tag:Name", "Values": [tag_name]},
        {"Name": "instance-state-name", "Values": ["running"]},
    ])
    return resp["Reservations"][0]["Instances"][0]

@pytest.mark.integration
def test_both_target_groups_become_healthy(aws, settings, outputs):
    def all_healthy():
        for tier in settings.tiers:
            targets = aws.elbv2.describe_target_health(
                TargetGroupArn=outputs.tg_arn(tier.name)
            )["TargetHealthDescriptions"]
            if not targets or any(t["TargetHealth"]["State"] != "healthy" for t in targets):
                return False
        return True

    assert wait_until(all_healthy, timeout=420, interval=15), "Target groups never became healthy"

@pytest.mark.integration
def test_iam_policy_simulator_least_privilege(aws, settings):
    account_id = aws.sts.get_caller_identity()["Account"]
    db_arn = f"arn:aws:ssm:{settings.region}:{account_id}:parameter/{settings.db_password_param.lstrip('/')}"
    gemini_arn = f"arn:aws:ssm:{settings.region}:{account_id}:parameter/{settings.gemini_param_name.lstrip('/')}"

    assert _decision(aws, settings.weather.role_name, "ssm:GetParameter", db_arn) == "allowed"
    assert _decision(aws, settings.weather.role_name, "ssm:GetParameter", gemini_arn) != "allowed"

    assert _decision(aws, settings.advisor.role_name, "ssm:GetParameter", gemini_arn) == "allowed"
    assert _decision(aws, settings.advisor.role_name, "ssm:GetParameter", db_arn) != "allowed"

@pytest.mark.integration
def test_network_isolation_alb_only_and_private_db(aws, settings, outputs, db_outputs):
    weather_inst = _running_instance(aws, "weather-app")
    advisor_inst = _running_instance(aws, "advisor-app")

    assert not tcp_open(weather_inst["PublicIpAddress"], 3000, timeout=3.0)
    assert not tcp_open(advisor_inst["PublicIpAddress"], 3000, timeout=3.0)
    assert not tcp_open(db_outputs.db_host, 5432, timeout=3.0)

@pytest.mark.integration
def test_end_to_end_weather_cache_history_and_advisor(settings, outputs):
    weather_base = f"http://{outputs.alb_dns_name}:{settings.weather.listener_port}"
    advisor_base = f"http://{outputs.alb_dns_name}:{settings.advisor.listener_port}"

    st1, b1 = get_json(f"{weather_base}/weather?zip=98101")
    assert st1 == 200 and "forecast" in b1
    assert b1["cache"] == "miss"

    st2, b2 = get_json(f"{weather_base}/weather?zip=98101")
    assert st2 == 200 and b2["cache"] == "hit"

    st_hist, b_hist = get_json(f"{weather_base}/history")
    assert st_hist == 200 and b_hist["count"] >= 1

    assert get_json(f"{weather_base}/weather?zip=abc")[0] == 400
    assert get_json(f"{weather_base}/weather?zip=00000")[0] == 404

    st_adv, b_adv = get_json(f"{advisor_base}/advice?zip=98101")
    assert st_adv == 200 and bool(b_adv.get("advice"))
    assert b_adv.get("source") in ("gemini", "fallback")

    home = requests.get(f"{advisor_base}/", timeout=10)
    assert home.status_code == 200 and "<form" in home.text

@pytest.mark.chaos
def test_chaos_database_cutoff_graceful_degradation(aws, settings, outputs, db_outputs):
    weather_base = f"http://{outputs.alb_dns_name}:{settings.weather.listener_port}"
    weather_inst = _running_instance(aws, "weather-app")
    rule = [{
        "IpProtocol": "tcp", "FromPort": 5432, "ToPort": 5432,
        "UserIdGroupPairs": [{"GroupId": settings.app_sg_id}],
    }]

    try:
        aws.ec2.revoke_security_group_ingress(GroupId=db_outputs.db_security_group_id, IpPermissions=rule)
        subprocess.run(
            ["ssh", "-o", "StrictHostKeyChecking=no", "-i", f"{settings.key_name}.pem",
             f"ec2-user@{weather_inst['PublicIpAddress']}", "sudo systemctl restart weather"],
            check=True,
        )
        time.sleep(5)

        status, body = get_json(f"{weather_base}/weather?zip=98101")
        assert status == 200
        assert body["cache"] == "unavailable"
        assert get_json(f"{weather_base}/history")[0] == 503
    finally:
        aws.ec2.authorize_security_group_ingress(GroupId=db_outputs.db_security_group_id, IpPermissions=rule)
        time.sleep(35)

    status_after, body_after = get_json(f"{weather_base}/weather?zip=98101")
    assert status_after == 200 and body_after["cache"] in ("hit", "miss")

@pytest.mark.chaos
def test_chaos_weather_tier_termination_and_recovery(aws, settings, outputs):
    weather_base = f"http://{outputs.alb_dns_name}:{settings.weather.listener_port}"
    advisor_base = f"http://{outputs.alb_dns_name}:{settings.advisor.listener_port}"

    group = aws.autoscaling.describe_auto_scaling_groups(
        AutoScalingGroupNames=[settings.weather.asg_name]
    )["AutoScalingGroups"][0]
    victim = [i["InstanceId"] for i in group["Instances"] if i["LifecycleState"] == "InService"][0]

    aws.autoscaling.terminate_instance_in_auto_scaling_group(
        InstanceId=victim, ShouldDecrementDesiredCapacity=False
    )
    started = time.time()

    time.sleep(15)
    adv_status, adv_body = get_json(f"{advisor_base}/advice?zip=33101", timeout=25)
    assert adv_status == 502
    assert adv_body.get("error") == "weather_service_unavailable"

    recovered = wait_until(lambda: get_json(f"{weather_base}/weather?zip=98101", timeout=5)[0] == 200, timeout=300, interval=10)
    elapsed = time.time() - started
    print(f"\nWeather service recovered in {elapsed:.1f}s")
    assert recovered and elapsed <= 300