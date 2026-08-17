from __future__ import annotations

import hashlib

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
)

from ovpn_bot.docker_logic import UserCertificateInfo


CREATE_PROFILE_BUTTON = "➕ Создать конфиг"
PROFILES_BUTTON = "📋 Конфиги"
STATUS_BUTTON = "📊 Статус"
SETTINGS_BUTTON = "⚙️ Настройки"


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [CREATE_PROFILE_BUTTON],
            [PROFILES_BUTTON, STATUS_BUTTON],
            [SETTINGS_BUTTON],
        ],
        resize_keyboard=True,
    )


def setup_protocol_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "UDP — быстрее",
                    callback_data="setup:protocol:udp",
                )
            ],
            [
                InlineKeyboardButton(
                    "TCP — порт 443",
                    callback_data="setup:protocol:tcp",
                )
            ],
        ]
    )


def setup_confirmation_keyboard(protocol: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🚀 Запустить VPN",
                    callback_data=f"setup:confirm:{protocol}",
                )
            ],
            [InlineKeyboardButton("← Назад", callback_data="setup:back")],
        ]
    )


def profile_token(common_name: str) -> str:
    return hashlib.sha256(common_name.encode("utf-8")).hexdigest()[:12]


def profile_actions_keyboard(
    users: list[UserCertificateInfo],
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for user in users:
        token = profile_token(user.common_name)
        rows.append(
            [
                InlineKeyboardButton(
                    f"⬇️ {user.base_name}",
                    callback_data=f"profile:download:{token}",
                ),
                InlineKeyboardButton(
                    "🗑 Отозвать",
                    callback_data=f"profile:revoke:{token}",
                ),
            ]
        )
    rows.append(
        [InlineKeyboardButton("🔄 Обновить", callback_data="profiles:refresh")]
    )
    return InlineKeyboardMarkup(rows)


def profile_revoke_confirmation_keyboard(token: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "Да, отозвать доступ",
                    callback_data=f"profile:confirm:{token}",
                )
            ],
            [InlineKeyboardButton("Отмена", callback_data="profile:cancel")],
        ]
    )


def settings_keyboard(has_suffix: bool) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                "✏️ Изменить суффикс",
                callback_data="settings:suffix",
            )
        ]
    ]
    if has_suffix:
        rows.append(
            [
                InlineKeyboardButton(
                    "Очистить суффикс",
                    callback_data="settings:suffix:clear",
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                "⚠️ Удалить VPN и сертификаты",
                callback_data="shutdown:request",
            )
        ]
    )
    return InlineKeyboardMarkup(rows)


def shutdown_confirmation_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "Да, удалить всё",
                    callback_data="shutdown:confirm",
                )
            ],
            [InlineKeyboardButton("Отмена", callback_data="shutdown:cancel")],
        ]
    )

