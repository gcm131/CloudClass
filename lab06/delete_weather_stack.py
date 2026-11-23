#!/usr/bin/env python3
"""Tear down the two-tier Weather Advisor stack."""
import argparse
import logging
from stack.clients import AwsClients
from stack.config import Settings
from stack.runner import delete_weather_stack

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", default=".env")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    settings = Settings.from_file(args.env)
    delete_weather_stack(settings, AwsClients.create(settings.region))

if __name__ == "__main__":
    main()