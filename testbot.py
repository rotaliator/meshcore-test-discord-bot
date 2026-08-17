import asyncio
from pprint import pformat

from meshcore import MeshCore, EventType
from meshcoredecoder import MeshCoreDecoder
from meshcoredecoder.crypto import MeshCoreKeyStore
from meshcoredecoder.types.crypto import DecryptionOptions
from meshcoredecoder.types.enums import PayloadType
from cachetools import TTLCache
from functools import wraps
import json
import logging
import sys
import discord
from discord.ext import commands

with open("testbot.json") as f:
    config = json.load(f)

# Configure logging based on config
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Remove any existing handlers
logger.handlers.clear()

formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

if config.get("log_to_stdout", True):
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(formatter)
    logger.addHandler(stdout_handler)

log_file = config.get("log_file")
if log_file:
    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

SERIAL_PORT = config.get("serial_port", "/dev/ttyACM0")
CHANNELS = set(config.get("channels"))
MAX_QUOTE_SIZE = int(config.get("max_quote_size", "20"))
WINDOW_SECONDS = int(config.get("window_seconds", "6"))
DISCORD_BOT_TOKEN = config.get("discord_bot_token")
MC_CHAN_TO_DISCORD_CHAN_ID = config.get("mc_chan_to_discord_chan_id", {})

key_store = MeshCoreKeyStore({"channel_secrets": config.get("channel_secrets", [])})
decryption_options = DecryptionOptions(key_store=key_store)


# global state
mesh = None
channels = {}
discord_bot = None
discord_ready = asyncio.Event()
companion_settings = {}


def filter_events(CHANNELS):
    """
    Decorator that filters messages based on channel, sender, and trigger conditions.
    Only passes events that meet all criteria to the decorated function.
    """

    def decorator(func):
        @wraps(func)
        async def wrapper(event):
            payload = event.payload
            try:
                # Check channel
                chan_name = payload.get("chan_name")
                if chan_name not in CHANNELS:
                    return None

                # Decrypt and validate message
                message = decrypt_message(payload["payload"])
                if not message:
                    return None

                # Check sender is not a bot
                sender = message.get("sender")
                if is_bot_name(sender):
                    return None

                # Check for trigger word/phrase
                text = message.get("message")
                if not contains_trigger(text):
                    return None

                # All conditions passed - execute the decorated function
                return await func(event)

            except Exception as e:
                logging.error(f"Error filtering message: {e}")
                return None

        return wrapper

    return decorator


def once_per_pkt_hash(ttl=20, maxsize=10000):
    seen = TTLCache(maxsize=maxsize, ttl=ttl)

    def decorator(func):
        @wraps(func)
        async def wrapper(event):
            pkt_hash = event.payload.get("pkt_hash")
            logging.info(f"pkt_hash: {pkt_hash}")

            if pkt_hash in seen:
                logging.info(f"Already processed package {pkt_hash}")
                return None

            seen[pkt_hash] = True
            return await func(event)

        return wrapper

    return decorator


def batch_by_pkt_hash(window_seconds=6, maxsize=10000):
    """
    Batches events by pkt_hash over a time window, then calls func with the list of events.
    Events with the same hash arriving after the window are ignored.
    """
    # Cache to track which hashes are currently being batched
    active_batches = TTLCache(maxsize=maxsize, ttl=window_seconds)
    # Store collected events per hash
    batches = {}

    def decorator(func):
        @wraps(func)
        async def wrapper(event):
            if not await func(event):
                return

            pkt_hash = event.payload.get("pkt_hash")

            if pkt_hash is None:
                return await func(event)

            # If hash already processed (expired from cache), ignore
            if pkt_hash not in active_batches and pkt_hash in batches:
                logging.info(f"Ignoring late package {pkt_hash}")
                return None

            # First event for this hash - start batching
            if pkt_hash not in batches:
                batches[pkt_hash] = [event]
                active_batches[pkt_hash] = True

                # Schedule batch processing after window_seconds
                asyncio.create_task(_process_batch_after_delay(pkt_hash))
                logging.info(f"Started batch for {pkt_hash}")
            else:
                # Add to existing batch
                batches[pkt_hash].append(event)
                logging.info(
                    f"Added to batch {pkt_hash} (total: {len(batches[pkt_hash])})"
                )

            return None

        async def _process_batch_after_delay(pkt_hash):
            await asyncio.sleep(window_seconds)
            if pkt_hash in batches:
                events_to_process = batches.pop(pkt_hash)
                await process_batch_events(events_to_process)

        return wrapper

    return decorator

def format_paths(events, path_hash_size):
    paths = []
    for n, event in enumerate(events, start=1):
        payload = event.payload
        path = payload.get("path")
        paths.append(f"path{n}={format_path(path, path_hash_size)}")
    return paths

def format_paths_compact(events, path_hash_size, min_common_hops=3):
    """
    Format paths using references to previously defined paths when this
    results in a shorter representation.

    A path can reference any previous path if:
    - they share at least `min_common_hops` consecutive hops from the beginning
    - the compact representation is shorter than the full representation

    Args:
        events: Iterable of events containing path information.
        path_hash_size: Hash size passed to format_path().
        min_common_hops: Minimum number of common hops required to use
                         a path reference. Defaults to 3.

    Returns:
        A list of compactly formatted path strings.
    """

    # First convert all paths to lists of formatted hop hashes.
    all_paths = []

    for event in events:
        payload = event.payload
        path = payload.get("path")

        formatted = format_path(path, path_hash_size)
        hops = formatted.split(",") if formatted else []

        all_paths.append(hops)

    result = []

    for i, current_path in enumerate(all_paths):
        path_number = i + 1

        # Full representation is always our fallback.
        full_path = ",".join(current_path)
        best = f"path{path_number}={full_path}"

        # Check all previously defined paths as possible references.
        for j in range(i):
            previous_path = all_paths[j]

            # Find the length of the common prefix.
            common = 0

            while (
                common < len(previous_path)
                and common < len(current_path)
                and previous_path[common] == current_path[common]
            ):
                common += 1

            # Only use a reference if enough hops are shared.
            if common < min_common_hops:
                continue

            # Everything after the common prefix is the suffix.
            suffix = current_path[common:]

            if suffix:
                candidate = (
                    f"path{path_number}=path{j + 1}+{','.join(suffix)}"
                )
            else:
                # The current path is identical to the previous one.
                candidate = f"path{path_number}=path{j + 1}"

            # Keep the compact representation only if it actually saves space.
            if len(candidate) < len(best):
                best = candidate

        result.append(best)

    return result

def prepare_response(events):
    payload = events[0].payload
    message = decrypt_message(payload["payload"])
    if not message:
        return
    sender = message.get("sender")
    text = message.get("message")
    path_hash_size = payload.get("path_hash_size", 1)

    paths = format_paths_compact(events, path_hash_size, min_common_hops=2)
    path_info = "; ".join(paths)
    response = format_batch_response(text, sender, path_hash_size, path_info)
    return response

async def send_mc_message(message, chan_name):
    splitted_message = split_message(message)
    for msg in splitted_message:
        result = await mesh.commands.send_chan_msg(channels[chan_name], msg)
        if result.type == EventType.ERROR:
            logging.error(f"MC send error: {result.payload}")
        await asyncio.sleep(1)


async def send_response(response, chan_name):
    logging.info(f"Reply: {response}")
    await send_mc_message(response, chan_name)

    # Send response to discord
    logging.info(f"send_response -> send_to_discord; {chan_name} {response}")
    bot_name = companion_settings.get("name")
    message = {"sender": bot_name,
               "message": response}
    result = await send_to_discord(chan_name, message)
    if result.type == EventType.ERROR:
        logging.error(f"Discord send error: {result.payload}")


async def process_batch_events(events):
    logging.info(f"process_batch_events:\n{pformat(events)}")
    if not events:
        return
    try:
        payload = events[0].payload
        chan_name = payload.get("chan_name")
        response = prepare_response(events)
        await send_response(response, chan_name)
    except Exception as e:
        logging.error(f"Handler error: {e}")


def contains_trigger(text: str) -> bool:
    text = text.lower()
    return text.startswith("test")


def is_bot_name(name: str) -> bool:
    return "bot" in name.lower()


def format_path(path, path_hash_size=1):
    if not path:
        return "direct"

    if isinstance(path, list):
        return ",".join(str(x) for x in path)

    return ",".join(
        [
            path[i : i + path_hash_size * 2]
            for i in range(0, len(path), path_hash_size * 2)
        ]
    )


def decrypt_message(payload):
    encrypted_packet = MeshCoreDecoder.decode(payload, decryption_options)
    if (
        encrypted_packet.payload_type == PayloadType.GroupText
        and encrypted_packet.payload.get("decoded")
    ):
        text = encrypted_packet.payload["decoded"]
        return text.decrypted


def format_response(text, sender, hops, path_hash_size, path):
    text = text.strip()
    if len(text) > MAX_QUOTE_SIZE:
        text = text[: MAX_QUOTE_SIZE - 3] + "..."

    response = (
        f"@[{sender}]"
        f"re: {text} | "
        f"hops={hops} | "
        f"bytes/hop={path_hash_size} | "
        f"path={format_path(path, path_hash_size)}"
    )
    return response


def format_batch_response(text, sender, path_hash_size, path_info):
    text = text.strip()
    if len(text) > MAX_QUOTE_SIZE:
        text = text[: MAX_QUOTE_SIZE - 3] + "..."

    response = f"@[{sender}]re: {text} | bytes={path_hash_size} | {path_info}"
    return response


def split_message(message, max_length=115, split_at=" |;,+"):
    if len(message) <= max_length:
        return [message]

    def split_chunk(text, limit):
        if len(text) <= limit:
            return [text]
        cut = -1
        for i in range(limit - 1, -1, -1):
            if text[i] in split_at:
                cut = i
                break
        if cut == -1:
            cut = limit
        else:
            cut += 1  # include separator
        first = text[:cut]
        rest = text[cut:].lstrip()
        return [first] + split_chunk(rest, limit)

    raw_parts = split_chunk(message, max_length)
    total = len(raw_parts)
    result = []
    for idx, part in enumerate(raw_parts, start=1):
        result.append(f"{idx}/{total} {part}".strip())
    return result


async def send_to_discord(chan_name: str, message: dict):
    """Send a MeshCore message to the corresponding Discord channel."""
    discord_chan_id = MC_CHAN_TO_DISCORD_CHAN_ID.get(chan_name)
    if not discord_chan_id or not discord_bot:
        return

    if not discord_bot.is_ready():
        logging.warning("Discord bot not ready, skipping message")
        return

    sender = message.get("sender", "unknown")
    text = message.get("message", "")

    discord_msg = f"**[{sender}]** {text}"

    logging.info(f"Attempting to send to Discord channel {discord_chan_id}")
    channel = discord_bot.get_channel(discord_chan_id)
    if channel:
        await channel.send(discord_msg)
        logging.info(f"Sent to Discord channel {discord_chan_id}: {discord_msg}")
    else:
        logging.warning(f"Discord channel {discord_chan_id} not found")


async def start_discord_bot():
    """Initialize and start Discord bot in background."""
    global discord_bot

    if not DISCORD_BOT_TOKEN:
        logging.warning("No Discord bot token configured")
        discord_ready.set()
        return

    intents = discord.Intents.default()
    intents.message_content = True
    discord_bot = commands.Bot(command_prefix='!', intents=intents)

    @discord_bot.event
    async def on_ready():
        logging.info(f'Discord bot logged in as {discord_bot.user}')
        discord_ready.set()

    try:
        await discord_bot.start(DISCORD_BOT_TOKEN)
    except Exception as e:
        logging.error(f"Discord bot failed to start: {e}")
        discord_ready.set()


async def main():
    logging.info(f"Connecting to {SERIAL_PORT} ...")
    global mesh
    try:
        mesh = await MeshCore.create_serial(
            SERIAL_PORT,
            115200,
            debug=False,
            auto_reconnect=True,
            max_reconnect_attempts=sys.maxsize,
        )
    except Exception as e:
        logging.error(e)
        exit(1)
    logging.info("Connected.")

    result = await mesh.commands.send_appstart()

    if result.type == EventType.ERROR:
        logging.error(f"Error getting device info: {pformat(result.payload)}")
        exit(1)
    global companion_settings
    companion_settings = result.payload
    logging.info(f"companion_settings = {pformat(companion_settings)}")
    logging.info(f"name = {companion_settings.get('name')}")

    await mesh.start_auto_message_fetching()

    global channels
    for idx in range(8):
        try:
            result = await mesh.commands.get_channel(idx)
            if result.type == EventType.ERROR:
                continue

            payload = result.payload

            name = payload.get("name") or payload.get("channel_name") or ""
            channels[name] = idx
            logging.info(f"Channel {idx}: {name}")

        except Exception as e:
            logging.error(f"Channel read error {idx}: {e}")

    # Start Discord bot in background (non-blocking)
    discord_task = asyncio.create_task(start_discord_bot())

    # Wait for Discord to be ready (with timeout)
    try:
        await asyncio.wait_for(discord_ready.wait(), timeout=60)
    except asyncio.TimeoutError:
        logging.warning("Discord bot did not become ready within 60 seconds")

    @batch_by_pkt_hash(window_seconds=WINDOW_SECONDS)
    @filter_events(CHANNELS)
    async def channel_handler(event: EventType):
        logging.info(f"event:\n{pformat(event)}")
        return event

    @once_per_pkt_hash(ttl=20)
    async def discord_forwarder(event):
        """Forward MeshCore messages to Discord."""
        payload = event.payload
        chan_name = payload.get("chan_name")
        # Only forward channels that have Discord mapping
        if chan_name not in MC_CHAN_TO_DISCORD_CHAN_ID:
            return
        message = decrypt_message(payload["payload"])
        if not message:
            return
        # Do not forward messages sent by Bot
        sender = message.get('sender')
        bot_name = companion_settings.get('name')
        logging.info(f"sender = {sender}; bot_name = {bot_name};")

        if sender == bot_name:
            logging.info(f"Skipping forwarding message sent by {bot_name}")
            return

        logging.info(f"discord_forwarder: forwarding {pformat(message)} from {sender} on {chan_name}")
        await send_to_discord(chan_name, message)

    async def main_handler(event: EventType):
        logging.info(f"main_handler: received event type {event.type}")
        await channel_handler(event)
        await discord_forwarder(event)

    mesh.subscribe(EventType.RX_LOG_DATA, main_handler)

    logging.info("Bot running.")

    while True:
        await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())
