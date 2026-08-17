from __future__ import annotations

import asyncio

import httpx
import pytest
from telegram.error import TimedOut
from telegram.request import HTTPXRequest


def _connect_timeout() -> TimedOut:
    try:
        raise httpx.ConnectTimeout("temporary route failure")
    except httpx.ConnectTimeout as error:
        try:
            raise TimedOut from error
        except TimedOut as wrapped_error:
            return wrapped_error


def _read_timeout() -> TimedOut:
    try:
        raise httpx.ReadTimeout("response may already have been accepted")
    except httpx.ReadTimeout as error:
        try:
            raise TimedOut from error
        except TimedOut as wrapped_error:
            return wrapped_error


def test_retrying_request_retries_connect_timeout(monkeypatch) -> None:
    from ovpn_bot.telegram_request import RetryingHTTPXRequest

    attempts = 0

    async def flaky_request(*args, **kwargs) -> tuple[int, bytes]:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise _connect_timeout()
        return 200, b'{"ok": true}'

    monkeypatch.setattr(HTTPXRequest, "do_request", flaky_request)
    request = RetryingHTTPXRequest(retry_attempts=3, retry_delay=0)

    async def execute() -> tuple[int, bytes]:
        try:
            return await request.do_request("https://api.telegram.org/test", "POST")
        finally:
            await request.shutdown()

    result = asyncio.run(execute())

    assert result == (200, b'{"ok": true}')
    assert attempts == 3


def test_retrying_request_does_not_retry_read_timeout(monkeypatch) -> None:
    from ovpn_bot.telegram_request import RetryingHTTPXRequest

    attempts = 0

    async def timed_out_request(*args, **kwargs) -> tuple[int, bytes]:
        nonlocal attempts
        attempts += 1
        raise _read_timeout()

    monkeypatch.setattr(HTTPXRequest, "do_request", timed_out_request)
    request = RetryingHTTPXRequest(retry_attempts=3, retry_delay=0)

    async def execute() -> None:
        try:
            with pytest.raises(TimedOut):
                await request.do_request("https://api.telegram.org/test", "POST")
        finally:
            await request.shutdown()

    asyncio.run(execute())

    assert attempts == 1
