"""Pure-function unit tests for IAM policies and EC2 user-data."""
import base64
from stack.compute import build_user_data, launch_template_data
from stack.policies import policy_for, trust_policy

ACCOUNT_ID = "123456789012"

def test_trust_policy_only_trusts_ec2():
    stmt = trust_policy()["Statement"][0]
    assert stmt["Principal"] == {"Service": "ec2.amazonaws.com"}
    assert stmt["Action"] == "sts:AssumeRole"

def test_weather_role_policy_only_reads_db_password(fake_settings):
    policy = policy_for("weather", fake_settings, ACCOUNT_ID)
    stmts = policy["Statement"]
    assert len(stmts) == 1
    assert stmts[0]["Effect"] == "Allow"
    assert stmts[0]["Action"] == ["ssm:GetParameter"]
    expected_arn = f"arn:aws:ssm:{fake_settings.region}:{ACCOUNT_ID}:parameter/test/db-password"
    assert stmts[0]["Resource"] == expected_arn
    assert "gemini" not in str(policy).lower()

def test_advisor_role_policy_only_reads_gemini_key(fake_settings):
    policy = policy_for("advisor", fake_settings, ACCOUNT_ID)
    stmts = policy["Statement"]
    assert len(stmts) == 1
    assert stmts[0]["Effect"] == "Allow"
    assert stmts[0]["Action"] == ["ssm:GetParameter"]
    expected_arn = f"arn:aws:ssm:{fake_settings.region}:{ACCOUNT_ID}:parameter/test/gemini-api-key"
    assert stmts[0]["Resource"] == expected_arn
    assert "db-password" not in str(policy).lower()

def test_alb_first_ordering_and_secret_exclusion_in_user_data(fake_settings):
    alb_dns = "my-alb-123.us-east-2.elb.amazonaws.com"
    db_host = "mydb.abc123.us-east-2.rds.amazonaws.com"

    advisor_ud = build_user_data(fake_settings, fake_settings.advisor, alb_dns_name=alb_dns, db_host=db_host)
    assert f"WEATHER_URL=http://{alb_dns}:8080" in advisor_ud
    assert db_host not in advisor_ud

    weather_ud = build_user_data(fake_settings, fake_settings.weather, alb_dns_name=alb_dns, db_host=db_host)
    assert f"DB_HOST={db_host}" in weather_ud
    assert "DB_PASSWORD=" not in weather_ud

def test_user_data_is_under_16kb_limit(fake_settings):
    alb_dns = "my-alb-123.us-east-2.elb.amazonaws.com"
    db_host = "mydb.abc123.us-east-2.rds.amazonaws.com"
    for tier in fake_settings.tiers:
        data = launch_template_data(fake_settings, tier, alb_dns_name=alb_dns, db_host=db_host)
        raw_bytes = base64.b64decode(data["UserData"])
        assert len(raw_bytes) < 16384, f"{tier.name} user-data exceeded 16 KB ({len(raw_bytes)} bytes)"