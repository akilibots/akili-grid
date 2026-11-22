"""Strategy configuration; credentials come from environment variables."""
from runtime import load_config


def config():
    return load_config()
