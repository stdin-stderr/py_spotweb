"""NNTP client provider for the API."""

from __future__ import annotations

from src.config import NNTPConfig
from src.scanner.nntp import NNTPClient


def get_nntp_client(cfg: NNTPConfig) -> NNTPClient:
    """Return an initialized NNTPClient."""
    client = NNTPClient(
        host=cfg.host,
        port=cfg.port,
        ssl=cfg.ssl,
        username=cfg.username,
        password=cfg.password,
    )
    return client
