"""IAM policy documents as pure Python dictionaries."""
from __future__ import annotations
from .config import Settings

def trust_policy() -> dict:
    """Who may assume the role: the EC2 service, nobody else."""
    return {
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {"Service": "ec2.amazonaws.com"},
            "Action": "sts:AssumeRole",
        }],
    }

def parameter_arn(region: str, account_id: str, param_name: str) -> str:
    """Build a valid SSM parameter ARN regardless of leading slash."""
    clean = param_name.lstrip("/")
    return f"arn:aws:ssm:{region}:{account_id}:parameter/{clean}"

def weather_policy(region: str, account_id: str, db_password_param: str) -> dict:
    """Read only the database password parameter."""
    return {
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Action": ["ssm:GetParameter"],
            "Resource": parameter_arn(region, account_id, db_password_param),
        }],
    }

def advisor_policy(region: str, account_id: str, gemini_param_name: str) -> dict:
    """Read only the Gemini API key parameter."""
    return {
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Action": ["ssm:GetParameter"],
            "Resource": parameter_arn(region, account_id, gemini_param_name),
        }],
    }

def policy_for(tier_name: str, settings: Settings, account_id: str) -> dict:
    if tier_name == "weather":
        return weather_policy(settings.region, account_id, settings.db_password_param)
    if tier_name == "advisor":
        return advisor_policy(settings.region, account_id, settings.gemini_param_name)
    raise ValueError(f"Unknown tier: {tier_name}")