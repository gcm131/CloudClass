"""Run create/delete database and stack functions against moto (no real AWS)."""
import pytest
from botocore.exceptions import ClientError
from moto import mock_aws
from stack.clients import AwsClients
from stack.config import Settings
from stack.database import create_database, delete_database
from stack.runner import create_weather_stack, delete_weather_stack
from tests.conftest import FAKE_VALUES

@pytest.fixture
def moto_env(tmp_path, monkeypatch, fake_settings):
    monkeypatch.chdir(tmp_path)
    with mock_aws():
        aws = AwsClients.create("us-east-2")
        vpc = aws.ec2.describe_vpcs(Filters=[{"Name": "isDefault", "Values": ["true"]}])["Vpcs"][0]
        app_sg = aws.ec2.create_security_group(
            GroupName="app-sg", Description="app", VpcId=vpc["VpcId"]
        )["GroupId"]
        aws.ec2.authorize_security_group_ingress(
            GroupId=app_sg,
            IpPermissions=[{
                "IpProtocol": "tcp", "FromPort": 3000, "ToPort": 3000,
                "IpRanges": [{"CidrIp": "0.0.0.0/0"}],
            }],
        )
        aws.ec2.create_key_pair(KeyName="test-key")
        ami = aws.ec2.describe_images()["Images"][0]["ImageId"]
        aws.ssm.put_parameter(Name="/test/gemini-api-key", Type="SecureString", Value="fake-gemini-key")

        values = dict(FAKE_VALUES, APP_SECURITY_GROUP_ID=app_sg, AMI_ID=ami)
        settings = Settings.from_values(values, base_dir=fake_settings.weather.app_dir.parent)
        yield settings, aws

def test_database_configuration_and_security_group(moto_env):
    settings, aws = moto_env
    db_out = create_database(settings, aws, wait=False)
    db_out.save()

    inst = aws.rds.describe_db_instances(DBInstanceIdentifier=settings.db_instance_id)["DBInstances"][0]
    assert inst["DBInstanceClass"] == "db.t4g.micro"
    assert inst["Engine"] == "postgres"
    assert inst["AllocatedStorage"] == 20
    assert inst["BackupRetentionPeriod"] == 0
    assert inst["MultiAZ"] is False
    assert inst["PubliclyAccessible"] is False
    assert inst["StorageEncrypted"] is True

    sg = aws.ec2.describe_security_groups(GroupIds=[db_out.db_security_group_id])["SecurityGroups"][0]
    rules = [p for p in sg["IpPermissions"] if p.get("FromPort") == 5432]
    assert len(rules) == 1
    assert rules[0]["IpRanges"] == []
    assert [p["GroupId"] for p in rules[0]["UserIdGroupPairs"]] == [settings.app_sg_id]

def test_database_create_and_delete_leaves_no_leftovers(moto_env):
    settings, aws = moto_env
    create_database(settings, aws, wait=False).save()
    delete_database(settings, aws, wait=False, sleep=lambda _: None)

    assert aws.rds.describe_db_instances()["DBInstances"] == []
    assert aws.rds.describe_db_snapshots()["DBSnapshots"] == []
    with pytest.raises(ClientError) as err:
        aws.ssm.get_parameter(Name=settings.db_password_param)
    assert err.value.response["Error"]["Code"] == "ParameterNotFound"

def test_full_stack_create_idempotency_and_delete(moto_env):
    settings, aws = moto_env
    db_out = create_database(settings, aws, wait=False)
    db_out.save()

    first = create_weather_stack(settings, aws, db_outputs=db_out, iam_wait=0, sleep=lambda _: None)
    second = create_weather_stack(settings, aws, db_outputs=db_out, iam_wait=0, sleep=lambda _: None)
    assert first == second

    assert len(aws.elbv2.describe_load_balancers()["LoadBalancers"]) == 1
    assert len(aws.elbv2.describe_target_groups()["TargetGroups"]) == 2
    assert len(aws.autoscaling.describe_auto_scaling_groups()["AutoScalingGroups"]) == 2

    delete_weather_stack(settings, aws, sleep=lambda _: None)
    assert aws.elbv2.describe_load_balancers()["LoadBalancers"] == []
    assert aws.autoscaling.describe_auto_scaling_groups()["AutoScalingGroups"] == []
    assert aws.iam.list_roles()["Roles"] == []