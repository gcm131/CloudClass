"""IAM roles, inline least-privilege policies, and instance profiles."""
from __future__ import annotations
import json
import logging
from .clients import AwsClients
from .config import Settings, Tier
from .policies import policy_for, trust_policy
from .util import ignore_errors

log = logging.getLogger("stack")

def ensure_role_and_profile(aws: AwsClients, settings: Settings, tier: Tier, account_id: str) -> None:
    """Create the role, its least-privilege inline policy, and instance profile."""
    with ignore_errors("EntityAlreadyExists"):
        aws.iam.create_role(
            RoleName=tier.role_name,
            AssumeRolePolicyDocument=json.dumps(trust_policy()),
        )
    aws.iam.put_role_policy(
        RoleName=tier.role_name,
        PolicyName=tier.policy_name,
        PolicyDocument=json.dumps(policy_for(tier.name, settings, account_id)),
    )
    with ignore_errors("EntityAlreadyExists"):
        aws.iam.create_instance_profile(InstanceProfileName=tier.profile_name)

    profile = aws.iam.get_instance_profile(InstanceProfileName=tier.profile_name)
    roles = [r["RoleName"] for r in profile["InstanceProfile"]["Roles"]]
    if tier.role_name not in roles:
        aws.iam.add_role_to_instance_profile(
            InstanceProfileName=tier.profile_name, RoleName=tier.role_name
        )
    log.info("%s role and instance profile are ready.", tier.name)

def delete_role_and_profile(aws: AwsClients, tier: Tier) -> None:
    """Remove instance profile, inline/managed policies, and IAM role."""
    with ignore_errors("NoSuchEntity"):
        aws.iam.remove_role_from_instance_profile(
            InstanceProfileName=tier.profile_name, RoleName=tier.role_name
        )
    with ignore_errors("NoSuchEntity"):
        aws.iam.delete_instance_profile(InstanceProfileName=tier.profile_name)
    with ignore_errors("NoSuchEntity"):
        aws.iam.delete_role_policy(RoleName=tier.role_name, PolicyName=tier.policy_name)
    with ignore_errors("NoSuchEntity"):
        attached = aws.iam.list_attached_role_policies(RoleName=tier.role_name)
        for policy in attached["AttachedPolicies"]:
            aws.iam.detach_role_policy(RoleName=tier.role_name, PolicyArn=policy["PolicyArn"])
    with ignore_errors("NoSuchEntity"):
        aws.iam.delete_role(RoleName=tier.role_name)
    log.info("Removed %s role and instance profile.", tier.name)