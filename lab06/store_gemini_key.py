#!/usr/bin/env python3
"""Prompt securely for the Gemini API key and store it in SSM Parameter Store."""
import getpass
from stack.clients import AwsClients
from stack.config import Settings

def main() -> None:
    settings = Settings.from_file(".env")
    aws = AwsClients.create(settings.region)
    key = getpass.getpass("Enter Gemini API key (input hidden): ").strip()
    if not key:
        raise SystemExit("Error: Empty key provided.")
    aws.ssm.put_parameter(
        Name=settings.gemini_param_name,
        Type="SecureString",
        Value=key,
        Overwrite=True,
    )
    print(f"Stored SecureString parameter: {settings.gemini_param_name}")

if __name__ == "__main__":
    main()