#!/usr/bin/env python3
"""Build the two-tier Weather Advisor stack."""
import argparse
import logging
from stack.clients import AwsClients
from stack.config import Settings
from stack.runner import create_weather_stack

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", default=".env")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    settings = Settings.from_file(args.env)
    outputs = create_weather_stack(settings, AwsClients.create(settings.region))
    outputs.save()
    print(f"\nDone. ALB DNS: {outputs.alb_dns_name}")
    print(f"Weather: http://{outputs.alb_dns_name}:{settings.weather.listener_port}/weather?zip=60616")
    print(f"Advisor: http://{outputs.alb_dns_name}:{settings.advisor.listener_port}/")

if __name__ == "__main__":
    main()