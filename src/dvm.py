"""Nostr DVM service for nsec leak checking."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import timedelta
from typing import TYPE_CHECKING

from nostr_sdk import (
    Client,
    EventBuilder,
    Filter,
    Keys,
    Kind,
    NostrSigner,
    RelayUrl,
    Tag,
    Timestamp,
    nip44_encrypt,
)

if TYPE_CHECKING:
    from src.checker import LeakChecker

logger = logging.getLogger(__name__)

JOB_REQUEST_KIND = Kind(5300)
JOB_RESULT_KIND = Kind(6300)
FETCH_TIMEOUT = timedelta(seconds=30)
POLL_INTERVAL = 5


class DvmService:
    """NIP-90 DVM that checks if a pubkey's nsec has been leaked."""

    def __init__(
        self,
        keys: Keys,
        checker: LeakChecker,
        relays: list[str],
    ) -> None:
        self._keys = keys
        self._signer = NostrSigner.keys(keys)
        self._checker = checker
        self._relays = relays
        self._client = Client(self._signer)
        self._processed_ids: set[str] = set()

    async def start(self) -> None:
        for relay in self._relays:
            await self._client.add_relay(RelayUrl.parse(relay))
        await self._client.connect()

        self._last_fetch_ts = Timestamp.now()

        logger.info(
            "DVM started | pubkey=%s | relays=%s | dataset=%d keys",
            self._keys.public_key().to_hex(),
            self._relays,
            self._checker.total_keys,
        )

        while True:
            try:
                await self._poll()
            except Exception as e:
                logger.error("Poll error: %s", e)
            await asyncio.sleep(POLL_INTERVAL)

    async def _poll(self) -> None:
        fetch_ts = Timestamp.now()
        f = Filter().kind(JOB_REQUEST_KIND).since(self._last_fetch_ts)
        events = await self._client.fetch_events(f, FETCH_TIMEOUT)

        for event in events.to_vec():
            event_id = event.id().to_hex()
            if event_id in self._processed_ids:
                continue
            self._processed_ids.add(event_id)

            try:
                await self._handle_job_request(event)
            except Exception as e:
                logger.error("Failed to handle event %s: %s", event_id[:16], e)

        self._last_fetch_ts = fetch_ts

        if len(self._processed_ids) > 10_000:
            self._processed_ids.clear()

    async def _handle_job_request(self, event) -> None:
        requester = event.author()
        requester_hex = requester.to_hex()

        logger.info("Job request from %s", requester_hex[:16])

        is_leaked = self._checker.is_leaked(requester_hex)

        if is_leaked:
            leak_info = self._checker.get_leak_info(requester_hex)
            leak_events = self._checker.get_leak_events(requester_hex)

            result = {
                "status": "leaked",
                "categories": leak_info.categories if leak_info else "",
                "events": leak_events,
            }
            logger.info(
                "LEAKED | pubkey=%s | categories=%s | events=%d",
                requester_hex[:16],
                leak_info.categories if leak_info else "",
                len(leak_events),
            )
        else:
            result = {"status": "safe", "events": []}
            logger.info("SAFE | pubkey=%s", requester_hex[:16])

        result_json = json.dumps(result, ensure_ascii=False)

        encrypted = nip44_encrypt(
            self._keys.secret_key(),
            requester,
            result_json,
        )

        result_event = (
            EventBuilder(JOB_RESULT_KIND, encrypted)
            .tag(Tag.parse(["p", requester_hex]))
            .tag(Tag.parse(["e", event.id().to_hex()]))
            .tag(Tag.parse(["encrypted"]))
            .tag(Tag.parse(["status", "success"]))
        )

        await self._client.send_event_builder(result_event)
        logger.info("Result sent to %s", requester_hex[:16])

    async def stop(self) -> None:
        await self._client.disconnect()
        logger.info("DVM stopped")
