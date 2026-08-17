from __future__ import annotations

import asyncio
import importlib

import pytest


def test_detector_skips_private_address_and_returns_public_ipv4() -> None:
    public_ip = importlib.import_module("ovpn_bot.public_ip")
    responses = iter(["10.0.0.2\n", "8.8.8.8\n"])

    async def fetcher(_url: str) -> str:
        return next(responses)

    detected = asyncio.run(
        public_ip.detect_public_ipv4(fetcher=fetcher, services=("first", "second"))
    )

    assert detected == "8.8.8.8"


def test_detector_reports_failure_when_no_public_ipv4_is_available() -> None:
    public_ip = importlib.import_module("ovpn_bot.public_ip")

    async def fetcher(_url: str) -> str:
        return "192.168.1.15"

    with pytest.raises(RuntimeError, match="public IPv4"):
        asyncio.run(public_ip.detect_public_ipv4(fetcher=fetcher, services=("only",)))

