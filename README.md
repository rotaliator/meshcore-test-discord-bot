# MeshCore-Test-Discord Bot

A bot that bridges MeshCore radio messages to Discord and responds to "test" triggers.

## Features

- Listens on configured MeshCore channels for messages starting with "test"
- Responds with routing information (path, hops, bytes/hop)
- Replies using the same region (flood scope) as the triggering message, when recognized
- Forwards MeshCore messages to Discord channels
- Tags forwarded messages with the region (e.g. `[region: pl-lu]`) and a link to the packet analyzer
- Batches duplicate packets within a configurable time window
- Decrypts MeshCore group text messages

## Configuration

Copy `testbot.json.sample` to `testbot.json` and edit:

```json
{
    "serial_port": "/dev/ttyACM0",
    "channels": ["#bot-test"],
    "channel_secrets": [
        "eee642a078e17d90283fbdf4b743eef4"
    ],
    "log_file": "testbot.log",
    "discord_bot_token": "your_discord_bot_token",
    "mc_chan_to_discord_chan_id": {
        "#bot-test": 123456789012345678
    },
    "add_corescope_link": true,
    "corescope_url": "https://analyzer.marwoj.net/#/map?packet={corescope_hash}",
    "regions": ["#pl", "#pl-lu", "#pl-sk", "#pl-mz"]
}
```

`testbot.json.sample` is the authoritative config shape. Note that `channel_secrets` is a flat list of hex strings (not a list of objects).

## Regions

MeshCore repeaters use **regions** (flood scope) to limit which packets are flooded. Region info is carried in the packet header as a transport code (only for `TransportFlood`/`TransportDirect` route types).

The `regions` list configures which region names the bot recognizes. For each forwarded message the bot derives the transport code from the region name and the packet payload, matches it against the incoming packet, and:

- tags the Discord message with `[region: <name>]` (only when a region is recognized), and
- replies to "test" messages using the same region as the trigger.

Messages sent without a region (plain flood) are unaffected.

## Installation

1. Clone the repo
2. Install dependencies:
   - Runtime: `pip install -r requirements.txt`
   - Development (with testing): `pip install -r requirements.txt -r requirements-dev.txt`
3. Configure `testbot.json`
4. Run: `python testbot.py`

## Requirements

- Python 3.8+
- MeshCore device connected via serial
- Discord bot token (optional, for Discord bridging)

## Testing

```bash
python -m pytest
```
