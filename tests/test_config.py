from __future__ import annotations

from ovpn_bot.config import load_settings


def test_settings_read_bot_token_from_secret_file(tmp_path, monkeypatch) -> None:
    token_file = tmp_path / "bot_token"
    token_file.write_text("123456:secret-token\n", encoding="utf-8")
    monkeypatch.delenv("BOT_TOKEN", raising=False)
    monkeypatch.setenv("BOT_TOKEN_FILE", str(token_file))
    monkeypatch.setenv("ADMIN_TELEGRAM_ID", "12345")
    monkeypatch.setenv("STATE_FILE", str(tmp_path / "state.json"))
    monkeypatch.setenv("OPENVPN_IMAGE", "openvpn:test")

    settings = load_settings()

    assert settings.bot_token == "123456:secret-token"
    assert settings.admin_ids == [12345]
    assert settings.state_file == str(tmp_path / "state.json")
    assert settings.openvpn_image == "openvpn:test"


def test_direct_bot_token_remains_supported(monkeypatch) -> None:
    monkeypatch.setenv("BOT_TOKEN", "123456:local-token")
    monkeypatch.delenv("BOT_TOKEN_FILE", raising=False)
    monkeypatch.setenv("ADMIN_TELEGRAM_ID", "12345")
    monkeypatch.delenv("STATE_FILE", raising=False)
    monkeypatch.delenv("OPENVPN_IMAGE", raising=False)

    settings = load_settings()

    assert settings.bot_token == "123456:local-token"
    assert settings.state_file.endswith("data/state.json")
    assert settings.openvpn_image == "kylemanna/openvpn:2.4"

