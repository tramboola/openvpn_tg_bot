from __future__ import annotations

import asyncio
import ipaddress
from collections.abc import Awaitable, Callable, Sequence
from urllib.request import Request, urlopen


PUBLIC_IP_SERVICES = (
    "https://api.ipify.org",
    "https://ifconfig.me/ip",
    "https://icanhazip.com",
)

PublicIpFetcher = Callable[[str], Awaitable[str]]


def _parse_public_ipv4(raw_value: str) -> str:
    candidate = raw_value.strip()
    address = ipaddress.ip_address(candidate)
    if address.version != 4 or not address.is_global:
        raise ValueError("Address is not a public IPv4")
    return str(address)


def _fetch_public_ip_sync(url: str) -> str:
    request = Request(url, headers={"User-Agent": "openvpn-tg-bot/1.1"})
    with urlopen(request, timeout=5) as response:  # noqa: S310 - fixed trusted URLs
        return response.read(64).decode("ascii", errors="strict")


async def _default_fetcher(url: str) -> str:
    return await asyncio.to_thread(_fetch_public_ip_sync, url)


async def detect_public_ipv4(
    fetcher: PublicIpFetcher | None = None,
    services: Sequence[str] = PUBLIC_IP_SERVICES,
) -> str:
    selected_fetcher = fetcher or _default_fetcher
    for service in services:
        try:
            return _parse_public_ipv4(await selected_fetcher(service))
        except (OSError, UnicodeError, ValueError):
            continue
    raise RuntimeError("Could not detect a public IPv4 address")

