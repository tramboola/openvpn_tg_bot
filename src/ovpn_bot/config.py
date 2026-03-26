from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(slots=True)
class Settings:
    bot_token: str
    admin_ids: list[int]
    docker_bin: str


def _parse_admin_ids(raw_admin_ids: str) -> list[int]:
    parsed_admin_ids: list[int] = []
    for raw_admin_id in raw_admin_ids.split(","):
        stripped_admin_id = raw_admin_id.strip()
        if not stripped_admin_id:
            continue
        parsed_admin_ids.append(int(stripped_admin_id))
    return parsed_admin_ids


def load_settings() -> Settings:
    bot_token = os.getenv("BOT_TOKEN", "").strip()
    raw_admin_ids = os.getenv("ADMIN_TELEGRAM_ID", "").strip()
    docker_bin = os.getenv("DOCKER_BIN", "").strip() or "docker"

    if not bot_token:
        raise ValueError("Environment variable BOT_TOKEN is required")
    if not raw_admin_ids:
        raise ValueError("Environment variable ADMIN_TELEGRAM_ID is required")

    try:
        admin_ids = _parse_admin_ids(raw_admin_ids)
    except ValueError as error:
        raise ValueError("ADMIN_TELEGRAM_ID must contain integer IDs") from error

    if not admin_ids:
        raise ValueError("ADMIN_TELEGRAM_ID must contain at least one admin ID")

    return Settings(bot_token=bot_token, admin_ids=admin_ids, docker_bin=docker_bin)

