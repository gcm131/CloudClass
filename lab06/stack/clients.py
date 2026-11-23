"""One place that builds the boto3 clients the stack needs."""
from __future__ import annotations
from dataclasses import dataclass
import boto3

@dataclass
class AwsClients:
    sts: object
    ssm: object
    iam: object
    ec2: object
    rds: object
    elbv2: object
    autoscaling: object

    @classmethod
    def create(cls, region: str) -> "AwsClients":
        session = boto3.session.Session(region_name=region)
        return cls(
            sts=session.client("sts"),
            ssm=session.client("ssm"),
            iam=session.client("iam"),
            ec2=session.client("ec2"),
            rds=session.client("rds"),
            elbv2=session.client("elbv2"),
            autoscaling=session.client("autoscaling"),
        )