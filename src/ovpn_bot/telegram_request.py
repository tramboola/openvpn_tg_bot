from __future__ import annotations

import asyncio
from typing import Any

import httpx
from telegram.error import NetworkError
from telegram.request import HTTPXRequest


class RetryingHTTPXRequest(HTTPXRequest):
    __slots__ = ("_retry_attempts", "_retry_delay")

    def __init__(
        self,
        *,
        retry_attempts: int = 3,
        retry_delay: float = 0.5,
        **kwargs: Any,
    ) -> None:
        if retry_attempts < 1:
            raise ValueError("retry_attempts must be at least 1")
        if retry_delay < 0:
            raise ValueError("retry_delay cannot be negative")
        super().__init__(**kwargs)
        self._retry_attempts = retry_attempts
        self._retry_delay = retry_delay

    async def do_request(self, *args: Any, **kwargs: Any) -> tuple[int, bytes]:
        for attempt in range(1, self._retry_attempts + 1):
            try:
                return await super().do_request(*args, **kwargs)
            except NetworkError as error:
                connection_failed = isinstance(
                    error.__cause__,
                    (httpx.ConnectError, httpx.ConnectTimeout),
                )
                if not connection_failed or attempt == self._retry_attempts:
                    raise
                await asyncio.sleep(self._retry_delay * attempt)

        raise RuntimeError("Telegram request retry loop ended unexpectedly")
