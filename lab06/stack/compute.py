"""User-data and launch templates for weather and advisor tiers."""
from __future__ import annotations
import base64
import logging
from botocore.exceptions import ClientError
from .clients import AwsClients
from .config import Settings, Tier
from .util import error_code

log = logging.getLogger("stack")

def _b64_file(path) -> str:
    return base64.b64encode(path.read_bytes()).decode()

def build_user_data(settings: Settings, tier: Tier, alb_dns_name: str, db_host: str) -> str:
    """Build the EC2 boot script for either the weather or advisor tier."""
    app_js = _b64_file(tier.app_dir / "app.js")
    package_json = _b64_file(tier.app_dir / "package.json")

    if tier.name == "weather":
        extra_setup = (
            "dnf install -y postgresql15\n"
            "curl -sS -o /opt/app/rds-ca.pem https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem\n"
        )
        extra_env = (
            f'Environment="NWS_USER_AGENT=(itmo-444-544 weather lab, {settings.contact_email})"\n'
            f"Environment=DB_HOST={db_host}\n"
            f"Environment=DB_NAME={settings.db_name}\n"
            f"Environment=DB_USER={settings.db_user}\n"
            f"Environment=DB_PASSWORD_PARAM={settings.db_password_param}\n"
            f"Environment=CACHE_SECONDS={settings.cache_seconds}\n"
        )
    else:
        extra_setup = ""
        extra_env = (
            f"Environment=WEATHER_URL=http://{alb_dns_name}:{settings.weather.listener_port}\n"
            f"Environment=GEMINI_KEY_PARAM={settings.gemini_param_name}\n"
            f"Environment=GEMINI_MODEL={settings.gemini_model}\n"
            f"Environment=KEY_CACHE_SECONDS={settings.key_cache_seconds}\n"
        )

    return f"""#!/bin/bash
dnf update -y
dnf install -y nodejs
mkdir -p /opt/app
{extra_setup}echo "{app_js}" | base64 -d > /opt/app/app.js
echo "{package_json}" | base64 -d > /opt/app/package.json
cd /opt/app
npm install --omit=dev
cat > /etc/systemd/system/{tier.service_name}.service << 'SERVICE'
[Unit]
Description={tier.name} app
After=network.target

[Service]
Environment=PORT={settings.app_port}
Environment=AWS_REGION={settings.region}
{extra_env}WorkingDirectory=/opt/app
ExecStart=/usr/bin/node /opt/app/app.js
Restart=always
User=ec2-user

[Install]
WantedBy=multi-user.target
SERVICE
chown -R ec2-user:ec2-user /opt/app
systemctl daemon-reload
systemctl enable {tier.service_name}.service
systemctl start {tier.service_name}.service
"""

def launch_template_data(settings: Settings, tier: Tier, alb_dns_name: str, db_host: str) -> dict:
    user_data = build_user_data(settings, tier, alb_dns_name=alb_dns_name, db_host=db_host)
    return {
        "ImageId": settings.ami_id,
        "InstanceType": settings.instance_type,
        "KeyName": settings.key_name,
        "SecurityGroupIds": [settings.app_sg_id],
        "IamInstanceProfile": {"Name": tier.profile_name},
        "UserData": base64.b64encode(user_data.encode()).decode(),
        "TagSpecifications": [{
            "ResourceType": "instance",
            "Tags": [{"Key": "Name", "Value": f"{tier.name}-app"}],
        }],
    }

def launch_template_exists(aws: AwsClients, tier: Tier) -> bool:
    try:
        aws.ec2.describe_launch_templates(LaunchTemplateNames=[tier.lt_name])
        return True
    except ClientError as err:
        if error_code(err) != "InvalidLaunchTemplateName.NotFoundException":
            raise
        return False

def ensure_launch_template(
    aws: AwsClients, settings: Settings, tier: Tier, alb_dns_name: str, db_host: str
) -> int:
    data = launch_template_data(settings, tier, alb_dns_name=alb_dns_name, db_host=db_host)
    if not launch_template_exists(aws, tier):
        aws.ec2.create_launch_template(LaunchTemplateName=tier.lt_name, LaunchTemplateData=data)
        log.info("Created launch template %s", tier.lt_name)
        return 1
    response = aws.ec2.create_launch_template_version(
        LaunchTemplateName=tier.lt_name, SourceVersion="1", LaunchTemplateData=data
    )
    version = response["LaunchTemplateVersion"]["VersionNumber"]
    log.info("Template %s exists, published version %s", tier.lt_name, version)
    return version

def delete_launch_template(aws: AwsClients, tier: Tier) -> None:
    if launch_template_exists(aws, tier):
        aws.ec2.delete_launch_template(LaunchTemplateName=tier.lt_name)
        log.info("Deleted launch template %s", tier.lt_name)