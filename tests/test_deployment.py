from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(shutil.which("docker") is None, reason="Docker CLI is unavailable")
def test_compose_config_mounts_state_and_bot_token_secret(tmp_path) -> None:
    shutil.copy2(PROJECT_ROOT / "docker-compose.yml", tmp_path / "docker-compose.yml")
    (tmp_path / ".env").write_text(
        "ADMIN_TELEGRAM_ID=12345\n"
        "STATE_FILE=/app/data/state.json\n"
        "OPENVPN_IMAGE=kylemanna/openvpn:2.4\n",
        encoding="utf-8",
    )
    secret_directory = tmp_path / "secrets"
    secret_directory.mkdir()
    (secret_directory / "bot_token").write_text(
        "123456:test-token\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            "docker",
            "compose",
            "--project-directory",
            str(tmp_path),
            "config",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "/app/data" in result.stdout
    assert "bot_token" in result.stdout
    assert "/usr/bin/docker" not in result.stdout


@pytest.mark.skipif(os.name == "nt", reason="Installer syntax is checked in WSL")
def test_installer_has_valid_bash_syntax() -> None:
    result = subprocess.run(
        ["bash", "-n", str(PROJECT_ROOT / "install.sh")],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr

