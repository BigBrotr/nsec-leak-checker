# nsec-leak-checker

A Nostr DVM (Data Vending Machine) that lets users check if their private key has been exposed in public events across the network.

## How It Works

1. A user sends a **Kind 5300** job request, signed with their keypair
2. The DVM verifies the request signature — this proves ownership of the pubkey being checked
3. The DVM searches its dataset of 16,000+ leaked nsec keys
4. The result is **encrypted with NIP-44** and sent back as a **Kind 6300** event, readable only by the requester

No one else can see the result. The signature on the request is the proof of identity — no additional verification needed.

## Public Instance

A live instance is running and can be queried by anyone:

| Field | Value |
|---|---|
| npub | `npub1jry923t9zkmqf0m2h99tlg3ak3xumg2h990ql3kujs5eher48v9qhv3ht5` |
| hex | `90c8552ad1616c24f6aba95abf447b5626e6945728b83fc6dc53932be3ea758a` |
| Relays | `wss://relay.damus.io`, `wss://nos.lol`, `wss://relay.primal.net`, `wss://relay.mostr.pub` |
| Request Kind | 5300 |
| Response Kind | 6300 (NIP-44 encrypted) |

### How to Query

Send a **Kind 5300** event signed with your keypair to any of the relays above. The event must include a `p` tag targeting the DVM's pubkey. The content can be anything — the DVM only checks the pubkey that signed the request.

**Using Python (nostr-sdk):**

```python
import asyncio
from datetime import timedelta
from nostr_sdk import (
    Client, EventBuilder, Filter, Keys, Kind,
    NostrSigner, PublicKey, RelayUrl, Tag,
    nip44_decrypt,
)

async def check_my_nsec():
    keys = Keys.parse("nsec1...")  # your nsec
    client = Client(NostrSigner.keys(keys))
    await client.add_relay(RelayUrl.parse("wss://relay.damus.io"))
    await client.connect()

    # Send job request (p-tag targets the DVM)
    await client.send_event_builder(
        EventBuilder(Kind(5300), "check").tags([
            Tag.parse(["p", "90c8552ad1616c24f6aba95abf447b5626e6945728b83fc6dc53932be3ea758a"])
        ])
    )

    # Wait and fetch response
    await asyncio.sleep(10)
    dvm = PublicKey.parse("90c8552ad1616c24f6aba95abf447b5626e6945728b83fc6dc53932be3ea758a")
    f = Filter().kind(Kind(6300)).author(dvm).pubkey(keys.public_key())
    events = await client.fetch_events(f, timedelta(seconds=10))

    for event in events.to_vec():
        decrypted = nip44_decrypt(keys.secret_key(), event.author(), event.content())
        print(decrypted)

    await client.disconnect()

asyncio.run(check_my_nsec())
```

**Using nak (CLI):**

```bash
# Send job request
nak event -k 5300 --sec nsec1... --content "check" -t p=90c8552ad1616c24f6aba95abf447b5626e6945728b83fc6dc53932be3ea758a wss://relay.damus.io

# Fetch response (replace <your-pubkey-hex> with your pubkey)
nak req -k 6300 --author 90c8552ad1616c24f6aba95abf447b5626e6945728b83fc6dc53932be3ea758a -t p=<your-pubkey-hex> wss://relay.damus.io
```

Note: the nak response will be NIP-44 encrypted — you'll need to decrypt it with your nsec.

## Dataset

The dataset was built by analyzing 40 million Nostr events archived by [BigBrotr](https://github.com/BigBrotr/bigbrotr) from 1,079 relays. See the [full analysis](https://bigbrotr.com/blog/exposed-nsec-analysis/) for methodology and findings.

| File | Description |
|---|---|
| `data/leaked_nsec_report.csv` | Pubkey, npub, nsec, event count, follower count, leak category |
| `data/leaked_nsec_events.jsonl` | Full Nostr events containing leaked nsec strings |

The data files are not included in the repository. Generate them using BigBrotr's database or request access.

## Setup

```bash
cp .env.example .env
```

Edit `.env`:

```
NOSTR_PRIVATE_KEY=nsec1...
```

## Run with Docker

```bash
docker compose up -d
docker compose logs -f
```

## Run locally

```bash
pip install .
NOSTR_PRIVATE_KEY=nsec1... python -m src.main
```

## Configuration

| Environment Variable | Required | Default | Description |
|---|---|---|---|
| `NOSTR_PRIVATE_KEY` | Yes | — | nsec or hex private key for the DVM |
| `DATA_DIR` | No | `data` | Path to directory containing dataset files |
| `RELAYS` | No | damus, nos.lol, primal, mostr | Comma-separated relay URLs |

## Response Format

The DVM responds with a NIP-44 encrypted JSON payload:

**If leaked:**

```json
{
  "status": "leaked",
  "categories": "profile_nsec_in_fields|bot_mr_nsec",
  "events": [
    {
      "id": "abc123...",
      "pubkey": "def456...",
      "kind": 0,
      "created_at": 1717524170,
      "tags": [],
      "content": "...",
      "sig": "..."
    }
  ]
}
```

**If safe:**

```json
{
  "status": "safe",
  "events": []
}
```

## Leak Categories

| Category | Description |
|---|---|
| `bot_mr_nsec` | Republished by automated bot with `Mr.{nsec}` profile pattern |
| `profile_nsec_in_fields` | nsec pasted into profile name, picture, nip05, or about fields |
| `ai_agent_logs` | AI agent published logs containing the nsec |
| `cli_command_leak` | CLI command with `--sec nsec1...` published in a note |
| `nsec_in_tags` | nsec embedded in event tags |
| `contactlist` | nsec used as relay URL in Kind 3 contact list |
| `note` | nsec appears in a Kind 1 note |

## License

MIT
