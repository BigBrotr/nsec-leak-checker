"""Leaked nsec dataset loader and checker."""

from __future__ import annotations

import csv
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class LeakedKey:
    pubkey: str
    nsec: str
    event_count: int
    follower_count: int
    categories: str


class LeakChecker:
    """Loads the leaked nsec dataset and checks pubkeys against it."""

    def __init__(self, report_path: Path, events_path: Path) -> None:
        self._keys: dict[str, LeakedKey] = {}
        self._events: dict[str, list[dict]] = {}  # pubkey -> list of events
        self._load_report(report_path)
        self._load_events(events_path)

    def _load_report(self, path: Path) -> None:
        with open(path, newline="") as f:
            reader = csv.reader(f)
            next(reader)  # skip header
            for row in reader:
                pubkey, _npub, nsec, event_count, follower_count, categories = row
                self._keys[pubkey] = LeakedKey(
                    pubkey=pubkey,
                    nsec=nsec,
                    event_count=int(event_count),
                    follower_count=int(follower_count),
                    categories=categories,
                )
        logger.info("Loaded %d leaked keys from %s", len(self._keys), path)

    def _load_events(self, path: Path) -> None:
        import re

        nsec_to_pubkey = {k.nsec: k.pubkey for k in self._keys.values()}

        with open(path) as f:
            for line in f:
                event = json.loads(line)
                content = event.get("content", "") or ""
                tags_str = json.dumps(event.get("tags", []))

                matches = set(re.findall(r"nsec1[a-z0-9]+", content, re.IGNORECASE))
                matches.update(re.findall(r"nsec1[a-z0-9]+", tags_str, re.IGNORECASE))

                for nsec in matches:
                    leaked_pubkey = nsec_to_pubkey.get(nsec)
                    if leaked_pubkey:
                        if leaked_pubkey not in self._events:
                            self._events[leaked_pubkey] = []
                        self._events[leaked_pubkey].append(event)

        total_events = sum(len(v) for v in self._events.values())
        logger.info(
            "Loaded events for %d pubkeys (%d total events) from %s",
            len(self._events),
            total_events,
            path,
        )

    def is_leaked(self, pubkey_hex: str) -> bool:
        return pubkey_hex in self._keys

    def get_leak_info(self, pubkey_hex: str) -> LeakedKey | None:
        return self._keys.get(pubkey_hex)

    def get_leak_events(self, pubkey_hex: str) -> list[dict]:
        return self._events.get(pubkey_hex, [])

    @property
    def total_keys(self) -> int:
        return len(self._keys)
