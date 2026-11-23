"""Shared fixtures for unit, integration, and chaos tests."""
from pathlib import Path
import pytest
from stack.clients import AwsClients
from stack.config import Settings
from stack.outputs import DbOutputs, StackOutputs

ROOT = Path(__file__).resolve().parent.parent

FAKE_VALUES = {
    "AWS_REGION": "us-east-2",
    "AMI_ID": "ami-12345678",
    "KEY_NAME": "test-key",
    "INSTANCE_TYPE": "t3.micro",
    "APP_SECURITY_GROUP_ID": "sg-app12345",
    "WEATHER_ROLE_NAME": "t-weather-role",
    "WEATHER_PROFILE_NAME": "t-weather-profile",
    "WEATHER_LT_NAME": "t-weather-lt",
    "WEATHER_TG_NAME": "t-weather-tg",
    "WEATHER_ASG_NAME": "t-weather-asg",
    "WEATHER_LISTENER_PORT": "8080",
    "ADVISOR_ROLE_NAME": "t-advisor-role",
    "ADVISOR_PROFILE_NAME": "t-advisor-profile",
    "ADVISOR_LT_NAME": "t-advisor-lt",
    "ADVISOR_TG_NAME": "t-advisor-tg",
    "ADVISOR_ASG_NAME": "t-advisor-asg",
    "ADVISOR_LISTENER_PORT": "8081",
    "ALB_NAME": "t-weather-alb",
    "ALB_SG_NAME": "t-weather-alb-sg",
    "AZ_A": "us-east-2a",
    "AZ_B": "us-east-2b",
    "DB_INSTANCE_ID": "t-weather-db",
    "DB_NAME": "weather",
    "DB_USER": "weatherapp",
    "DB_SG_NAME": "t-weather-db-sg",
    "DB_SUBNET_GROUP_NAME": "t-weather-db-subnets",
    "DB_PASSWORD_PARAM": "/test/db-password",
    "CACHE_SECONDS": "600",
    "GEMINI_PARAM_NAME": "/test/gemini-api-key",
    "GEMINI_MODEL": "gemini-3.1-flash-lite",
    "KEY_CACHE_SECONDS": "60",
    "CONTACT_EMAIL": "student@example.com",
}

@pytest.fixture
def fake_settings(tmp_path):
    """Settings pointing at tiny fake app folders so no real files are needed."""
    for name in ("weather-app", "advisor-app"):
        folder = tmp_path / name
        folder.mkdir()
        (folder / "app.js").write_text(f"console.log('{name}');\n")
        (folder / "package.json").write_text('{"name": "%s"}\n' % name)
    return Settings.from_values(FAKE_VALUES, base_dir=tmp_path)

@pytest.fixture(scope="session")
def settings():
    return Settings.from_file(ROOT / ".env")

@pytest.fixture(scope="session")
def aws(settings):
    return AwsClients.create(settings.region)

@pytest.fixture(scope="session")
def db_outputs():
    try:
        return DbOutputs.load(ROOT)
    except FileNotFoundError:
        pytest.skip("db_outputs.json not found. Run python3 create_database.py first.")

@pytest.fixture(scope="session")
def outputs():
    try:
        return StackOutputs.load(ROOT)
    except FileNotFoundError:
        pytest.skip("stack_outputs.json not found. Run python3 create_weather_stack.py first.")