from __future__ import annotations

import importlib


def test_runtime_state_round_trip(tmp_path) -> None:
    state_module = importlib.import_module("ovpn_bot.state")
    store = state_module.JsonStateStore(tmp_path / "state.json")
    expected = state_module.RuntimeState(
        server_protocol="udp",
        public_host="8.8.8.8",
        server_port=1194,
        profile_suffix="prague",
    )

    store.save(expected)

    assert store.load() == expected


def test_missing_state_file_loads_empty_state(tmp_path) -> None:
    state_module = importlib.import_module("ovpn_bot.state")
    store = state_module.JsonStateStore(tmp_path / "missing.json")

    assert store.load() == state_module.RuntimeState()


def test_state_rejects_incomplete_server_endpoint(tmp_path) -> None:
    state_module = importlib.import_module("ovpn_bot.state")
    store = state_module.JsonStateStore(tmp_path / "state.json")
    invalid_state = state_module.RuntimeState(server_protocol="udp")

    try:
        store.save(invalid_state)
    except ValueError as error:
        assert "server state" in str(error)
    else:
        raise AssertionError("Incomplete server state must be rejected")

