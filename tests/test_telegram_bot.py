from __future__ import annotations

import asyncio

from telegram.ext import CallbackQueryHandler, MessageHandler

from ovpn_bot.config import Settings
from ovpn_bot.docker_logic import UserCertificateInfo
from ovpn_bot.state import JsonStateStore, RuntimeState


class StubLogic:
    pass


class ProfilesLogic:
    async def list_users(self) -> list[UserCertificateInfo]:
        return [
            UserCertificateInfo(
                common_name="alena_UF01_udp",
                base_name="alena_UF01",
                protocol="udp",
                activated_at="Aug 17 10:15:55 2026 GMT",
            )
        ]


class RecordingMessage:
    def __init__(self) -> None:
        self.replies: list[tuple[str, dict[str, object]]] = []

    async def reply_text(self, text: str, **kwargs: object) -> None:
        self.replies.append((text, kwargs))


async def stub_public_ip_detector() -> str:
    return "8.8.8.8"


def test_bot_registers_callback_and_text_handlers(tmp_path) -> None:
    from ovpn_bot.telegram_bot import TelegramOvpnBot

    settings = Settings(
        bot_token="123456:test-token",
        admin_ids=[12345],
        docker_bin="docker-test",
        state_file=str(tmp_path / "state.json"),
        openvpn_image="openvpn:test",
    )
    bot = TelegramOvpnBot(
        settings,
        logic=StubLogic(),
        state_store=JsonStateStore(settings.state_file),
        public_ip_detector=stub_public_ip_detector,
    )
    handlers = [handler for group in bot.application.handlers.values() for handler in group]

    assert any(isinstance(handler, CallbackQueryHandler) for handler in handlers)
    assert any(
        isinstance(handler, MessageHandler)
        and not isinstance(handler, CallbackQueryHandler)
        for handler in handlers
    )


def test_bot_uses_retrying_requests_for_polling_and_responses(tmp_path) -> None:
    from ovpn_bot.telegram_bot import TelegramOvpnBot
    from ovpn_bot.telegram_request import RetryingHTTPXRequest

    settings = Settings(
        bot_token="123456:test-token",
        admin_ids=[12345],
        docker_bin="docker-test",
        state_file=str(tmp_path / "state.json"),
        openvpn_image="openvpn:test",
    )

    bot = TelegramOvpnBot(
        settings,
        logic=StubLogic(),
        state_store=JsonStateStore(settings.state_file),
        public_ip_detector=stub_public_ip_detector,
    )

    assert isinstance(bot.application.bot.request, RetryingHTTPXRequest)
    assert isinstance(bot.application.bot._request[0], RetryingHTTPXRequest)


def test_updating_suffix_persists_filename_only_setting(tmp_path) -> None:
    from ovpn_bot.telegram_bot import TelegramOvpnBot

    state_store = JsonStateStore(tmp_path / "state.json")
    state_store.save(
        RuntimeState(
            server_protocol="udp",
            public_host="8.8.8.8",
            server_port=1194,
        )
    )
    settings = Settings(
        bot_token="123456:test-token",
        admin_ids=[12345],
        docker_bin="docker-test",
        state_file=str(tmp_path / "state.json"),
        openvpn_image="openvpn:test",
    )
    bot = TelegramOvpnBot(
        settings,
        logic=StubLogic(),
        state_store=state_store,
        public_ip_detector=stub_public_ip_detector,
    )

    updated = bot.update_profile_suffix("prague")

    assert updated.profile_suffix == "prague"
    assert updated.server_protocol == "udp"
    assert state_store.load() == updated


def test_profiles_are_shown_only_as_buttons_without_text_list(tmp_path) -> None:
    from ovpn_bot.telegram_bot import TelegramOvpnBot

    state_store = JsonStateStore(tmp_path / "state.json")
    state_store.save(
        RuntimeState(
            server_protocol="udp",
            public_host="8.8.8.8",
            server_port=1194,
        )
    )
    settings = Settings(
        bot_token="123456:test-token",
        admin_ids=[12345],
        docker_bin="docker-test",
        state_file=str(tmp_path / "state.json"),
        openvpn_image="openvpn:test",
    )
    bot = TelegramOvpnBot(
        settings,
        logic=ProfilesLogic(),
        state_store=state_store,
        public_ip_detector=stub_public_ip_detector,
    )
    message = RecordingMessage()

    asyncio.run(bot._show_profiles(message))

    text, kwargs = message.replies[0]
    assert "alena_UF01" not in text
    assert "Aug 17" not in text
    markup = kwargs["reply_markup"]
    labels = [button.text for row in markup.inline_keyboard for button in row]
    assert any("alena_UF01" in label for label in labels)

