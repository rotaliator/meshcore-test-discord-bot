# MeshCore-Test-Discord Bot

A bot that bridges MeshCore radio messages to Discord and responds to "test" triggers.

## Features

- Listens on configured MeshCore channels for messages starting with "test"
- Responds with routing information (path, hops, bytes/hop)
- Forwards MeshCore messages to Discord channels
- Batches duplicate packets within a configurable time window
- Decrypts MeshCore group text messages

## Configuration

Copy `testbot.json.sample` to `testbot.json` and edit:

```json
{
    "serial_port": "/dev/ttyACM0",
    "channels": ["#bot-test"],
    "max_quote_size": 20,
    "window_seconds": 6,
    "discord_bot_token": "your_discord_bot_token",
    "mc_chan_to_discord_chan_id": {
        "#bot-test": 123456789012345678
    },
    "channel_secrets": [
        {"channel_name": "#bot-test", "secret": "your_secret"}
    ],
    "log_to_stdout": true,
    "log_file": null
}
```

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
