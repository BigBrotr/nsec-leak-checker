"""Entry point for the nsec leak checker DVM."""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

from nostr_sdk import Keys

from src.checker import LeakChecker
from src.dvm import DvmService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

DEFAULT_RELAYS = [
    "wss://relay.damus.io",
    "wss://nos.lol",
    "wss://relay.primal.net",
    "wss://relay.mostr.pub",
]


async def run() -> None:
    nsec = os.environ.get("NOSTR_PRIVATE_KEY")
    if not nsec:
        logger.error("NOSTR_PRIVATE_KEY environment variable is required")
        sys.exit(1)

    keys = Keys.parse(nsec)

    data_dir = Path(os.environ.get("DATA_DIR", "data"))
    report_path = data_dir / "leaked_nsec_report.csv"
    events_path = data_dir / "leaked_nsec_events.jsonl"

    if not report_path.exists():
        logger.error("Report file not found: %s", report_path)
        sys.exit(1)
    if not events_path.exists():
        logger.error("Events file not found: %s", events_path)
        sys.exit(1)

    relays_env = os.environ.get("RELAYS")
    relays = relays_env.split(",") if relays_env else DEFAULT_RELAYS

    checker = LeakChecker(report_path, events_path)
    dvm = DvmService(keys, checker, relays)

    try:
        await dvm.start()
    except KeyboardInterrupt:
        pass
    finally:
        await dvm.stop()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
