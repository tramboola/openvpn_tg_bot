from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path


PROTOCOL_PORTS = {"udp": 1194, "tcp": 443}


@dataclass(slots=True)
class RuntimeState:
    server_protocol: str | None = None
    public_host: str | None = None
    server_port: int | None = None
    profile_suffix: str = ""

    @property
    def is_initialized(self) -> bool:
        return all(
            (
                self.server_protocol,
                self.public_host,
                self.server_port is not None,
            )
        )

    def validate(self) -> None:
        endpoint_values = (
            self.server_protocol,
            self.public_host,
            self.server_port,
        )
        if any(value is not None for value in endpoint_values) and not all(
            value is not None for value in endpoint_values
        ):
            raise ValueError("Incomplete server state")
        if self.server_protocol is not None:
            expected_port = PROTOCOL_PORTS.get(self.server_protocol)
            if expected_port is None or self.server_port != expected_port:
                raise ValueError("Invalid server state protocol or port")


class JsonStateStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load(self) -> RuntimeState:
        if not self.path.exists():
            return RuntimeState()

        raw_data = json.loads(self.path.read_text(encoding="utf-8"))
        state = RuntimeState(
            server_protocol=raw_data.get("server_protocol"),
            public_host=raw_data.get("public_host"),
            server_port=raw_data.get("server_port"),
            profile_suffix=raw_data.get("profile_suffix", ""),
        )
        state.validate()
        return state

    def save(self, state: RuntimeState) -> None:
        state.validate()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.path.with_name(f"{self.path.name}.tmp")
        temporary_path.write_text(
            json.dumps(asdict(state), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary_path, self.path)

