#!/usr/bin/env python3
"""Delete the PostgreSQL RDS database with no snapshots or retained backups."""
import argparse
import logging
from stack.clients import AwsClients
from stack.config import Settings
from stack.database import delete_database

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", default=".env")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    settings = Settings.from_file(args.env)
    delete_database(settings, AwsClients.create(settings.region))

if __name__ == "__main__":
    main()