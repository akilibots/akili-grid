"""Configuration, durable state and logging for a standalone bot."""
import fcntl
import json
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pyjson5
import requests


def number(value):
    result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError("Numbers must be finite")
    return result


def load_config(name="strategy", path="data/strategy.json"):
    source = os.environ[name] if name in os.environ else Path(path).read_text()
    return pyjson5.decode(source)


class State:
    def __init__(self, path="data/state.json", initial=None):
        self.path = Path(path)
        self.data = json.loads(self.path.read_text()) if self.path.exists() else {"version": 4, **(initial or {})}
        if "version" not in self.data or self.data["version"] != 4:
            raise ValueError("Legacy state cannot be used on dYdX Chain. Reconcile old orders and archive the old state first.")

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        with temporary.open("w") as stream:
            json.dump(self.data, stream, default=str)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(self.path)


@contextmanager
def single_instance(path="data/bot.lock"):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def log(message, name="akilibots"):
    print(datetime.now(timezone.utc).isoformat(), name + ":", message, flush=True)
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat = os.environ.get("TELEGRAM_CHAT_ID", "")
    if token and chat:
        try:
            response = requests.post("https://api.telegram.org/bot" + token + "/sendMessage", json={"chat_id": chat, "text": name + ": " + message}, timeout=10)
            response.raise_for_status()
        except requests.RequestException:
            print("Telegram delivery failed", flush=True)
