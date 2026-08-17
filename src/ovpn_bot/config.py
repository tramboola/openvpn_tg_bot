from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class Settings:
    bot_token: str
    admin_ids: list[int]
    docker_bin: str
    state_file: str
    openvpn_image: str


def _parse_admin_ids(raw_admin_ids: str) -> list[int]:
    parsed_admin_ids: list[int] = []
    for raw_admin_id in raw_admin_ids.split(","):
        stripped_admin_id = raw_admin_id.strip()
        if not stripped_admin_id:
            continue
        parsed_admin_ids.append(int(stripped_admin_id))
    return parsed_admin_ids


def load_settings() -> Settings:
    bot_token_file = os.getenv("BOT_TOKEN_FILE", "").strip()
    if bot_token_file:
        try:
            bot_token = Path(bot_token_file).read_text(encoding="utf-8").strip()
        except OSError as error:
            raise ValueError(f"Cannot read BOT_TOKEN_FILE: {bot_token_file}") from error
    else:
        bot_token = os.getenv("BOT_TOKEN", "").strip()
    raw_admin_ids = os.getenv("ADMIN_TELEGRAM_ID", "").strip()
    docker_bin = os.getenv("DOCKER_BIN", "").strip() or "docker"
    state_file = os.getenv("STATE_FILE", "").strip() or "data/state.json"
    openvpn_image = os.getenv("OPENVPN_IMAGE", "").strip() or (
        "kylemanna/openvpn:2.4@"
        "sha256:4de5e6690818c7c4025ae605369f681e813a7f9fe5d99feed988412c2d07987c"
    )

    if not bot_token:
        raise ValueError("BOT_TOKEN or BOT_TOKEN_FILE is required")
    if not raw_admin_ids:
        raise ValueError("Environment variable ADMIN_TELEGRAM_ID is required")

    try:
        admin_ids = _parse_admin_ids(raw_admin_ids)
    except ValueError as error:
        raise ValueError("ADMIN_TELEGRAM_ID must contain integer IDs") from error

    if not admin_ids:
        raise ValueError("ADMIN_TELEGRAM_ID must contain at least one admin ID")

    return Settings(
        bot_token=bot_token,
        admin_ids=admin_ids,
        docker_bin=docker_bin,
        state_file=state_file,
        openvpn_image=openvpn_image,
    )

