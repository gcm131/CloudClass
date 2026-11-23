#!/usr/bin/env python3
"""Create the private PostgreSQL RDS database."""
import argparse
import logging
from stack.clients import AwsClients
from stack.config import Settings
from stack.database import create_database

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", default=".env")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    settings = Settings.from_file(args.env)
    outputs = create_database(settings, AwsClients.create(settings.region))
    outputs.save()
    print(f"\nDone. Database endpoint: {outputs.db_host}")

if __name__ == "__main__":
    main()