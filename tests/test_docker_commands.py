from __future__ import annotations

import asyncio

import pytest

from ovpn_bot.docker_logic import CommandResult, OvpnLogic


class RecordingLogic(OvpnLogic):
    def __init__(self) -> None:
        super().__init__(docker_bin="docker-test", openvpn_image="openvpn:test")
        self.commands: list[list[str]] = []
        self.volume_remove_fails = False

    async def _run_command(self, command: list[str]) -> CommandResult:
        self.commands.append(command)
        if any(argument.endswith("/index.txt") for argument in command):
            return CommandResult(
                output=(
                    "V\t270817000000Z\t\t00\tunknown\t/CN=185.5.206.191\n"
                    "V\t270817000000Z\t\t01\tunknown\t/CN=iphone_udp\n"
                    "R\t270817000000Z\t260817000000Z\t02\tunknown\t/CN=old_tcp"
                ),
                return_code=0,
            )
        if "-startdate" in command:
            return CommandResult(output="notBefore=Aug 17 10:00:00 2026 GMT", return_code=0)
        if self.volume_remove_fails and command[1:3] == ["volume", "rm"]:
            return CommandResult(output="volume is in use", return_code=1)
        return CommandResult(output="ok", return_code=0)


def test_init_starts_only_selected_udp_container() -> None:
    logic = RecordingLogic()

    asyncio.run(logic.command_init("udp", "8.8.8.8"))

    server_commands = [command for command in logic.commands if "-d" in command]
    assert len(server_commands) == 1
    assert "ovpn_udp" in server_commands[0]
    assert "1194:1194/udp" in server_commands[0]
    assert "ovpn_tcp" not in " ".join(" ".join(command) for command in logic.commands)
    assert "udp://8.8.8.8:1194" in " ".join(
        " ".join(command) for command in logic.commands
    )


def test_init_uses_fixed_tcp_port() -> None:
    logic = RecordingLogic()

    asyncio.run(logic.command_init("tcp", "8.8.8.8"))

    joined_commands = "\n".join(" ".join(command) for command in logic.commands)
    assert "ovpn_tcp" in joined_commands
    assert "443:1194/tcp" in joined_commands
    assert "tcp://8.8.8.8:443" in joined_commands
    assert "ovpn_udp" not in joined_commands


def test_list_users_returns_only_active_certificates_with_start_date() -> None:
    logic = RecordingLogic()

    users = asyncio.run(logic.list_users())

    assert len(users) == 1
    assert users[0].common_name == "iphone_udp"
    assert users[0].base_name == "iphone"
    assert users[0].protocol == "udp"
    assert users[0].activated_at == "Aug 17 10:00:00 2026 GMT"


def test_existing_profile_download_does_not_rebuild_certificate() -> None:
    logic = RecordingLogic()

    profile = asyncio.run(logic.command_get_profile("iphone_udp", "udp"))

    assert profile.endswith(b"\n")
    joined_commands = "\n".join(" ".join(command) for command in logic.commands)
    assert "ovpn_getclient iphone_udp" in joined_commands
    assert "build-client-full" not in joined_commands


def test_revoke_uses_resolved_common_name_without_reconstructing_it() -> None:
    logic = RecordingLogic()

    asyncio.run(logic.command_revoke_common_name("work_udp_tcp"))

    assert "ovpn_revokeclient work_udp_tcp remove" in " ".join(logic.commands[0])


def test_cleanup_does_not_report_success_when_volume_removal_fails() -> None:
    logic = RecordingLogic()
    logic.volume_remove_fails = True

    with pytest.raises(RuntimeError, match="volume is in use"):
        asyncio.run(logic.command_remove())
