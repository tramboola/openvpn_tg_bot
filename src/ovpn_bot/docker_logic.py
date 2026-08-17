from __future__ import annotations

import asyncio
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from ovpn_bot.state import PROTOCOL_PORTS

OVPN_PREFIX = "ovpn_"
OVPN_DATA_VOLUME = f"{OVPN_PREFIX}data"
OVPN_UDP_CONTAINER = f"{OVPN_PREFIX}udp"
OVPN_TCP_CONTAINER = f"{OVPN_PREFIX}tcp"
DEFAULT_OPENVPN_IMAGE = "kylemanna/openvpn:2.4"
DOCKER_LOG_OPTIONS = [
    "--log-driver",
    "json-file",
    "--log-opt",
    "max-size=3m",
    "--log-opt",
    "max-file=1",
]

ADDRESS_PATTERN = re.compile(r"(\w+)://([\w.]+):(\d+)")
SUPPORTED_CLIENT_PROTOCOLS = {"tcp", "udp"}
PROFILE_NAME_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,31}")
PROFILE_SUFFIX_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,23}")
COMMON_NAME_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,64}")


@dataclass(slots=True)
class CommandResult:
    output: str
    return_code: int


@dataclass(slots=True)
class UserCertificateInfo:
    common_name: str
    base_name: str
    protocol: str
    activated_at: str


def parse_address(address: str) -> tuple[str, str, str] | None:
    matched = ADDRESS_PATTERN.fullmatch(address)
    if not matched:
        return None
    protocol, host, port = matched.groups()
    return protocol, host, port


def split_long_message(text: str, max_chars: int = 3900) -> list[str]:
    if len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    remaining = text
    while len(remaining) > max_chars:
        split_position = remaining.rfind("\n", 0, max_chars)
        if split_position <= 0:
            split_position = max_chars
        chunks.append(remaining[:split_position])
        remaining = remaining[split_position:].lstrip("\n")
    if remaining:
        chunks.append(remaining)
    return chunks


def adapt_profile_for_protocol(profile_text: str, protocol: str) -> str:
    normalized_protocol = protocol.strip().lower()
    if normalized_protocol not in SUPPORTED_CLIENT_PROTOCOLS:
        raise ValueError(f"Unsupported protocol: {protocol}")

    input_lines = profile_text.splitlines()
    output_lines: list[str] = []
    protocol_was_set = False

    for input_line in input_lines:
        stripped_line = input_line.strip()
        if stripped_line.startswith("proto "):
            if not protocol_was_set:
                output_lines.append(f"proto {normalized_protocol}")
                protocol_was_set = True
            continue

        # explicit-exit-notify is useful for UDP, but usually not needed for TCP.
        if stripped_line.startswith("explicit-exit-notify"):
            continue

        output_lines.append(input_line)

    if not protocol_was_set:
        output_lines.insert(0, f"proto {normalized_protocol}")

    if normalized_protocol == "udp":
        output_lines.append("explicit-exit-notify 1")

    return "\n".join(output_lines).strip() + "\n"


def normalize_profile_name(profile_name: str) -> str:
    normalized_profile_name = profile_name.strip()
    if not PROFILE_NAME_PATTERN.fullmatch(normalized_profile_name):
        raise ValueError(
            "Profile name must contain 1-32 Latin letters, digits, '-' or '_'"
        )
    return normalized_profile_name


def normalize_profile_suffix(suffix: str) -> str:
    normalized_suffix = suffix.strip()
    if not normalized_suffix:
        return ""
    if not PROFILE_SUFFIX_PATTERN.fullmatch(normalized_suffix):
        raise ValueError(
            "Profile suffix must contain at most 24 Latin letters, digits, '-' or '_'"
        )
    return normalized_suffix


def build_profile_filename(profile_name: str, suffix: str, protocol: str) -> str:
    normalized_profile_name = normalize_profile_name(profile_name)
    normalized_suffix = normalize_profile_suffix(suffix)
    normalized_protocol = protocol.strip().lower()
    if normalized_protocol not in SUPPORTED_CLIENT_PROTOCOLS:
        raise ValueError("Protocol must be tcp or udp")

    suffix_part = f"-{normalized_suffix}" if normalized_suffix else ""
    return f"{normalized_profile_name}{suffix_part}-{normalized_protocol}.ovpn"


def build_client_common_name(profile_name: str, protocol: str) -> str:
    normalized_profile_name = normalize_profile_name(profile_name)
    normalized_protocol = protocol.strip().lower()
    if normalized_protocol not in SUPPORTED_CLIENT_PROTOCOLS:
        raise ValueError("Protocol must be tcp or udp")
    return f"{normalized_profile_name}_{normalized_protocol}"


def parse_common_name_to_user(common_name: str) -> tuple[str, str]:
    if common_name.endswith("_tcp"):
        return common_name[: -len("_tcp")], "tcp"
    if common_name.endswith("_udp"):
        return common_name[: -len("_udp")], "udp"
    return common_name, "unknown"


class OvpnLogic:
    def __init__(
        self,
        docker_bin: str = "docker",
        openvpn_image: str = DEFAULT_OPENVPN_IMAGE,
    ) -> None:
        self.docker_bin = self._resolve_docker_bin(docker_bin)
        self.openvpn_image = openvpn_image.strip() or DEFAULT_OPENVPN_IMAGE
        self._mutation_lock = asyncio.Lock()

    def _resolve_docker_bin(self, docker_bin: str) -> str:
        configured_value = docker_bin.strip()
        if configured_value and configured_value != "docker":
            return configured_value

        discovered_path = shutil.which("docker")
        if discovered_path:
            return discovered_path

        # Fallback paths help when bot runs under service managers
        # with a reduced PATH (common on Ubuntu/systemd).
        fallback_paths = [
            "/usr/bin/docker",
            "/usr/local/bin/docker",
            "/snap/bin/docker",
            r"C:\Program Files\Docker\Docker\resources\bin\docker.exe",
        ]
        for fallback_path in fallback_paths:
            if Path(fallback_path).exists():
                return fallback_path

        return "docker"

    def _with_docker(self, command_tail: list[str]) -> list[str]:
        return [self.docker_bin, *command_tail]

    async def _run_command(self, command: list[str]) -> CommandResult:
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
        except FileNotFoundError as error:
            linux_hint = "DOCKER_BIN=/usr/bin/docker"
            windows_hint = (
                r"DOCKER_BIN=C:\Program Files\Docker\Docker\resources\bin\docker.exe"
            )
            raise RuntimeError(
                "Docker CLI is not available. Install Docker Desktop/Engine and ensure "
                f"`{self.docker_bin}` is in PATH, or set DOCKER_BIN with full path.\n"
                f"Linux example: `{linux_hint}`\n"
                f"Windows example: `{windows_hint}`"
            ) from error
        stdout_data, _ = await process.communicate()
        text_output = stdout_data.decode("utf-8", errors="replace")
        return CommandResult(output=text_output.strip(), return_code=process.returncode)

    async def _execute_step(self, command: list[str]) -> str:
        command_text = " ".join(command)
        result = await self._run_command(command)
        message_lines = [f"Executing command: `{command_text}`"]
        if result.output:
            message_lines.append(result.output)
        if result.return_code != 0:
            raise RuntimeError("\n".join(message_lines))
        return "\n".join(message_lines)

    async def command_init(self, protocol: str, host: str) -> list[str]:
        normalized_protocol = protocol.strip().lower()
        if normalized_protocol not in PROTOCOL_PORTS:
            raise ValueError("Protocol must be tcp or udp")
        normalized_host = host.strip()
        if not normalized_host:
            raise ValueError("Public host cannot be empty")

        port = PROTOCOL_PORTS[normalized_protocol]
        address = f"{normalized_protocol}://{normalized_host}:{port}"
        container_name = f"{OVPN_PREFIX}{normalized_protocol}"
        data_mount = f"{OVPN_DATA_VOLUME}:/etc/openvpn"
        steps = [
            self._with_docker(["volume", "create", "--name", OVPN_DATA_VOLUME]),
            self._with_docker(
                [
                    "run",
                    "-v",
                    data_mount,
                    "--rm",
                    self.openvpn_image,
                    "ovpn_genconfig",
                    "-u",
                    address,
                ]
            ),
            self._with_docker(
                [
                    "run",
                    "-v",
                    data_mount,
                    "--rm",
                    "-e",
                    "EASYRSA_BATCH=1",
                    "-e",
                    f"EASYRSA_REQ_CN={normalized_host}",
                    self.openvpn_image,
                    "ovpn_initpki",
                    "nopass",
                ]
            ),
            [
                self.docker_bin,
                "run",
                "-v",
                data_mount,
                "-d",
                "--restart=always",
                "--name",
                container_name,
                *DOCKER_LOG_OPTIONS,
                "-p",
                f"{port}:1194/{normalized_protocol}",
                "--cap-add=NET_ADMIN",
                self.openvpn_image,
                "ovpn_run",
                "--proto",
                normalized_protocol,
            ],
        ]

        async with self._mutation_lock:
            messages = [await self._execute_step(command) for command in steps]
        messages.append(
            f"OpenVPN initialized: {normalized_protocol.upper()} on port {port}."
        )
        return messages

    async def command_remove(self) -> list[str]:
        messages: list[str] = []
        async with self._mutation_lock:
            for container_name in (OVPN_UDP_CONTAINER, OVPN_TCP_CONTAINER):
                command = self._with_docker(["rm", "-f", container_name])
                result = await self._run_command(command)
                if result.return_code != 0 and "No such container" not in result.output:
                    raise RuntimeError(result.output or f"Failed to remove {container_name}")
                messages.append(f"Container {container_name} removed or was absent.")

            volume_command = self._with_docker(["volume", "rm", OVPN_DATA_VOLUME])
            volume_result = await self._run_command(volume_command)
            if volume_result.return_code != 0:
                raise RuntimeError(volume_result.output or "Failed to remove OpenVPN data")
            messages.append("OpenVPN certificates and configuration were removed.")
        return messages

    async def command_status(self) -> str:
        command = self._with_docker(["ps", "--format", "{{.ID}} {{.Image}} {{.Names}} {{.Status}}"])
        result = await self._run_command(command)
        if result.return_code != 0:
            raise RuntimeError(result.output or "Failed to get docker status")

        all_lines = [line for line in result.output.splitlines() if line.strip()]
        ovpn_lines = [line for line in all_lines if " ovpn_" in f" {line}"]

        response_lines = [f"Total {len(all_lines)} containers:"]
        response_lines.extend(all_lines)
        response_lines.append("")
        response_lines.append(f"Total {len(ovpn_lines)} ovpn containers:")
        response_lines.extend(ovpn_lines)
        return "\n".join(response_lines).strip()

    async def list_users(self) -> list[UserCertificateInfo]:
        data_mount = f"{OVPN_DATA_VOLUME}:/etc/openvpn"
        index_command = self._with_docker(
            [
                "run",
                "-v",
                data_mount,
                "--rm",
                self.openvpn_image,
                "cat",
                "/etc/openvpn/pki/index.txt",
            ]
        )
        index_result = await self._run_command(index_command)
        if index_result.return_code != 0:
            raise RuntimeError(index_result.output or "Failed to read users from PKI index")

        users: list[UserCertificateInfo] = []
        for row in index_result.output.splitlines():
            if not row.startswith("V\t"):
                continue
            columns = row.split("\t")
            if len(columns) < 6:
                continue

            distinguished_name = columns[5]
            if "CN=" not in distinguished_name:
                continue

            common_name = distinguished_name.split("CN=", maxsplit=1)[1].strip()
            if common_name in {"server", "Easy-RSA CA"}:
                continue

            base_name, protocol = parse_common_name_to_user(common_name)
            users.append(
                UserCertificateInfo(
                    common_name=common_name,
                    base_name=base_name,
                    protocol=protocol,
                    activated_at=await self._get_certificate_activation_time(common_name),
                )
            )

        users.sort(key=lambda item: item.base_name.lower())
        return users

    async def command_users(self) -> str:
        users = await self.list_users()
        response_lines = [f"Total users: {len(users)}"]
        for user in users:
            response_lines.append(
                f"- {user.base_name} ({user.protocol}) | CN: {user.common_name} | active since: {user.activated_at}"
            )
        if not users:
            response_lines.append("No users found.")
        return "\n".join(response_lines)

    async def _get_certificate_activation_time(self, common_name: str) -> str:
        data_mount = f"{OVPN_DATA_VOLUME}:/etc/openvpn"
        cert_path = f"/etc/openvpn/pki/issued/{common_name}.crt"
        cert_command = self._with_docker(
            [
                "run",
                "-v",
                data_mount,
                "--rm",
                self.openvpn_image,
                "openssl",
                "x509",
                "-in",
                cert_path,
                "-noout",
                "-startdate",
            ]
        )
        cert_result = await self._run_command(cert_command)
        if cert_result.return_code != 0:
            return "unknown"

        output_value = cert_result.output.strip()
        if output_value.startswith("notBefore="):
            return output_value.replace("notBefore=", "", 1).strip()
        return output_value or "unknown"

    async def command_remove_user(self, profile_name: str, protocol: str) -> str:
        normalized_protocol = protocol.strip().lower()
        if normalized_protocol not in SUPPORTED_CLIENT_PROTOCOLS:
            raise ValueError("Protocol must be tcp or udp")
        client_common_name = build_client_common_name(profile_name, normalized_protocol)
        return await self.command_revoke_common_name(client_common_name)

    async def command_revoke_common_name(self, common_name: str) -> str:
        normalized_common_name = common_name.strip()
        if not COMMON_NAME_PATTERN.fullmatch(normalized_common_name):
            raise ValueError("Invalid certificate common name")

        data_mount = f"{OVPN_DATA_VOLUME}:/etc/openvpn"
        revoke_command = self._with_docker(
            [
                "run",
                "-v",
                data_mount,
                "--rm",
                "-e",
                "EASYRSA_BATCH=1",
                self.openvpn_image,
                "ovpn_revokeclient",
                normalized_common_name,
                "remove",
            ]
        )
        async with self._mutation_lock:
            revoke_result = await self._run_command(revoke_command)
        if revoke_result.return_code != 0:
            raise RuntimeError(revoke_result.output or "Failed to revoke user certificate")

        response_lines = [f"Certificate `{normalized_common_name}` revoked."]
        if revoke_result.output:
            response_lines.append(revoke_result.output)
        return "\n".join(response_lines)

    async def command_generate(self, profile_name: str, protocol: str = "tcp") -> bytes:
        if not profile_name:
            raise ValueError("Please provide profileName")
        normalized_protocol = protocol.strip().lower()
        if normalized_protocol not in SUPPORTED_CLIENT_PROTOCOLS:
            raise ValueError("Protocol must be tcp or udp")
        client_common_name = build_client_common_name(profile_name, normalized_protocol)

        data_mount = f"{OVPN_DATA_VOLUME}:/etc/openvpn"
        build_command = [
            self.docker_bin,
            "run",
            "-v",
            data_mount,
            "--rm",
            "-i",
            self.openvpn_image,
            "easyrsa",
            "build-client-full",
            client_common_name,
            "nopass",
        ]
        async with self._mutation_lock:
            build_result = await self._run_command(build_command)
            if build_result.return_code != 0:
                raise RuntimeError(
                    build_result.output or "Client profile generation failed"
                )
            return await self._get_profile_unlocked(
                common_name=client_common_name,
                protocol=normalized_protocol,
            )

    async def command_get_profile(self, common_name: str, protocol: str) -> bytes:
        normalized_common_name = common_name.strip()
        if not COMMON_NAME_PATTERN.fullmatch(normalized_common_name):
            raise ValueError("Invalid certificate common name")
        normalized_protocol = protocol.strip().lower()
        if normalized_protocol not in SUPPORTED_CLIENT_PROTOCOLS:
            raise ValueError("Protocol must be tcp or udp")
        async with self._mutation_lock:
            return await self._get_profile_unlocked(
                common_name=normalized_common_name,
                protocol=normalized_protocol,
            )

    async def _get_profile_unlocked(self, common_name: str, protocol: str) -> bytes:
        data_mount = f"{OVPN_DATA_VOLUME}:/etc/openvpn"
        get_client_command = [
            self.docker_bin,
            "run",
            "-v",
            data_mount,
            "--rm",
            self.openvpn_image,
            "ovpn_getclient",
            common_name,
        ]
        get_client_result = await self._run_command(get_client_command)
        if get_client_result.return_code != 0:
            raise RuntimeError(get_client_result.output or "Failed to fetch client profile")
        adapted_profile = adapt_profile_for_protocol(
            profile_text=get_client_result.output,
            protocol=protocol,
        )
        return adapted_profile.encode("utf-8")
