from __future__ import annotations

from ovpn_bot.docker_logic import UserCertificateInfo


def test_main_menu_contains_approved_actions() -> None:
    from ovpn_bot.telegram_ui import main_menu_keyboard

    labels = {
        button.text
        for row in main_menu_keyboard().keyboard
        for button in row
    }

    assert labels == {
        "➕ Создать конфиг",
        "📋 Конфиги",
        "📊 Статус",
        "⚙️ Настройки",
    }


def test_setup_keyboard_offers_only_udp_and_tcp() -> None:
    from ovpn_bot.telegram_ui import setup_protocol_keyboard

    buttons = [
        button
        for row in setup_protocol_keyboard().inline_keyboard
        for button in row
    ]

    assert [(button.text, button.callback_data) for button in buttons] == [
        ("UDP — быстрее", "setup:protocol:udp"),
        ("TCP — порт 443", "setup:protocol:tcp"),
    ]


def test_profile_callbacks_do_not_expose_certificate_common_name() -> None:
    from ovpn_bot.telegram_ui import profile_actions_keyboard

    common_name = "private_device_udp"
    markup = profile_actions_keyboard(
        [
            UserCertificateInfo(
                common_name=common_name,
                base_name="private_device",
                protocol="udp",
                activated_at="Aug 17 10:00:00 2026 GMT",
            )
        ]
    )
    callbacks = [
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
    ]

    assert all(common_name not in callback for callback in callbacks)
    assert callbacks[0].startswith("profile:download:")
    assert callbacks[1].startswith("profile:revoke:")


def test_profile_token_is_stable_and_short() -> None:
    from ovpn_bot.telegram_ui import profile_token

    first = profile_token("iphone_udp")
    second = profile_token("iphone_udp")

    assert first == second
    assert len(first) == 12

