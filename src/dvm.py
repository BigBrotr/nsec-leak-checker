"""Nostr DVM service for nsec leak checking."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import TYPE_CHECKING

from nostr_sdk import (
    Client,
    Event,
    EventBuilder,
    Filter,
    Keys,
    Kind,
    NostrSigner,
    PublicKey,
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

    async def start(self) -> None:
        for relay in self._relays:
            await self._client.add_relay(RelayUrl.parse(relay))
        await self._client.connect()

        logger.info(
            "DVM started | pubkey=%s | relays=%s | dataset=%d keys",
            self._keys.public_key().to_hex(),
            self._relays,
            self._checker.total_keys,
        )

        subscription = Filter().kind(JOB_REQUEST_KIND).since(Timestamp.now())
        await self._client.subscribe([subscription])

        await self._client.handle_notifications(self)

    async def handle(self, _relay_url: str, _subscription_id: str, event: Event) -> bool:
        """Called by nostr-sdk for each received event."""
        try:
            await self._handle_job_request(event)
        except Exception as e:
            logger.error("Failed to handle event %s: %s", event.id().to_hex()[:16], e)
        return False  # keep listening

    async def _handle_job_request(self, event: Event) -> None:
        requester = event.author()
        requester_hex = requester.to_hex()

        logger.info("Job request from %s", requester_hex[:16])

        # The requester is checking their own pubkey (proven by signature)
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

        # Encrypt with NIP-44
        encrypted = nip44_encrypt(
            self._keys.secret_key(),
            requester,
            result_json,
        )

        # Build result event
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
