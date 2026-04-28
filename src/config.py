"""Load configuration from config.toml, with .env / env-var overrides."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class NNTPConfig:
    host: str
    port: int
    ssl: bool
    username: str
    password: str
    max_connections: int
    batch_size: int


@dataclass
class DatabaseConfig:
    dsn: str


@dataclass
class ScannerConfig:
    spotnet_groups: list[str]
    max_age_days: int


@dataclass
class APIConfig:
    host: str
    port: int
    api_key: str
    base_url: str


@dataclass
class Config:
    nntp: NNTPConfig
    database: DatabaseConfig
    scanner: ScannerConfig
    api: APIConfig


def load(path: str | Path = "config.toml") -> Config:
    with open(path, "rb") as f:
        raw = tomllib.load(f)

    n = raw["nntp"]
    nntp = NNTPConfig(
        host=os.environ.get("NNTP_HOST", n["host"]),
        port=int(os.environ.get("NNTP_PORT", n["port"])),
        ssl=os.environ.get("NNTP_USE_SSL", str(n["ssl"])).lower() in ("true", "1", "yes"),
        username=os.environ.get("NNTP_USERNAME", n["username"]),
        password=os.environ.get("NNTP_PASSWORD", n["password"]),
        max_connections=n["max_connections"],
        batch_size=n["batch_size"],
    )

    db_dsn = os.environ.get("DATABASE_URL", raw["database"]["dsn"])
    database = DatabaseConfig(dsn=db_dsn)

    s = raw["scanner"]
    scanner = ScannerConfig(
        spotnet_groups=s.get("spotnet_groups", []),
        max_age_days=int(os.environ.get("MAX_AGE_DAYS", s["max_age_days"])),
    )

    a = raw["api"]
    api = APIConfig(
        host=a["host"],
        port=a["port"],
        api_key=a["api_key"],
        base_url=a["base_url"],
    )

    return Config(nntp=nntp, database=database, scanner=scanner, api=api)
