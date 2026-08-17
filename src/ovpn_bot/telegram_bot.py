from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import replace
from io import BytesIO

from telegram import BotCommand, InputFile, Message, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from ovpn_bot.config import Settings
from ovpn_bot.docker_logic import (
    OvpnLogic,
    UserCertificateInfo,
    build_profile_filename,
    normalize_profile_name,
    normalize_profile_suffix,
    split_long_message,
)
from ovpn_bot.public_ip import detect_public_ipv4
from ovpn_bot.state import JsonStateStore, PROTOCOL_PORTS, RuntimeState
from ovpn_bot.telegram_ui import (
    CREATE_PROFILE_BUTTON,
    PROFILES_BUTTON,
    SETTINGS_BUTTON,
    STATUS_BUTTON,
    main_menu_keyboard,
    profile_actions_keyboard,
    profile_revoke_confirmation_keyboard,
    profile_token,
    settings_keyboard,
    setup_confirmation_keyboard,
    setup_protocol_keyboard,
    shutdown_confirmation_keyboard,
)


PublicIpDetector = Callable[[], Awaitable[str]]


class TelegramOvpnBot:
    def __init__(
        self,
        settings: Settings,
        *,
        logic: OvpnLogic | None = None,
        state_store: JsonStateStore | None = None,
        public_ip_detector: PublicIpDetector = detect_public_ipv4,
    ) -> None:
        self.settings = settings
        self.logic = logic or OvpnLogic(
            settings.docker_bin,
            openvpn_image=settings.openvpn_image,
        )
        self.state_store = state_store or JsonStateStore(settings.state_file)
        self.state = self.state_store.load()
        self.public_ip_detector = public_ip_detector
        self.application = (
            Application.builder()
            .token(settings.bot_token)
            .post_init(self._post_init)
            .build()
        )
        self._register_handlers()

    async def _post_init(self, _application: Application) -> None:
        commands = [
            BotCommand("start", "Открыть главное меню"),
            BotCommand("generate", "Создать конфигурацию"),
            BotCommand("users", "Показать активные конфигурации"),
            BotCommand("status", "Показать состояние VPN"),
            BotCommand("settings", "Открыть настройки"),
            BotCommand("shutdown", "Удалить VPN с подтверждением"),
            BotCommand("help", "Показать справку"),
        ]
        await self.application.bot.set_my_commands(commands)

    def _register_handlers(self) -> None:
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("init", self.init_command))
        self.application.add_handler(CommandHandler("status", self.status_command))
        self.application.add_handler(CommandHandler("users", self.users_command))
        self.application.add_handler(CommandHandler("generate", self.generate_command))
        self.application.add_handler(
            CommandHandler("generate_tcp", self.generate_command)
        )
        self.application.add_handler(
            CommandHandler("generate_udp", self.generate_command)
        )
        self.application.add_handler(
            CommandHandler("settings", self.settings_command)
        )
        self.application.add_handler(
            CommandHandler("shutdown", self.shutdown_command)
        )
        self.application.add_handler(CallbackQueryHandler(self.callback_query))
        self.application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.text_message)
        )
        self.application.add_handler(
            MessageHandler(filters.COMMAND, self.unknown_command)
        )

    def _is_admin(self, update: Update) -> bool:
        user = update.effective_user
        return user is not None and user.id in self.settings.admin_ids

    async def _reply_forbidden(self, update: Update) -> None:
        if update.callback_query is not None:
            await update.callback_query.answer("Доступ запрещён", show_alert=True)
        elif update.effective_message is not None:
            await update.effective_message.reply_text("Доступ запрещён")

    async def _send_text_chunks(
        self,
        message: Message | None,
        text: str,
        **kwargs: object,
    ) -> None:
        if message is None:
            return
        chunks = split_long_message(text)
        for index, chunk in enumerate(chunks):
            await message.reply_text(chunk, **kwargs if index == len(chunks) - 1 else {})

    async def _show_home(self, update: Update) -> None:
        message = update.effective_message
        if message is None:
            return
        if not self.state.is_initialized:
            await message.reply_text(
                "VPN ещё не настроен. Выберите один протокол:",
                reply_markup=setup_protocol_keyboard(),
            )
            return
        await message.reply_text(
            "Главное меню",
            reply_markup=main_menu_keyboard(),
        )

    async def start_command(
        self,
        update: Update,
        _context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        if not self._is_admin(update):
            await self._reply_forbidden(update)
            return
        await self._show_home(update)

    async def help_command(
        self,
        update: Update,
        _context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        if not self._is_admin(update):
            await self._reply_forbidden(update)
            return
        await self._send_text_chunks(
            update.effective_message,
            "Управляйте VPN кнопками: создавайте конфиги, скачивайте их повторно "
            "и отзывайте доступ. Команды оставлены как резервный способ управления.",
            reply_markup=main_menu_keyboard() if self.state.is_initialized else None,
        )
        if not self.state.is_initialized:
            await self._show_home(update)

    async def init_command(
        self,
        update: Update,
        _context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        if not self._is_admin(update):
            await self._reply_forbidden(update)
            return
        if self.state.is_initialized:
            await self._send_text_chunks(
                update.effective_message,
                "VPN уже настроен. Для полного сброса используйте настройки.",
                reply_markup=main_menu_keyboard(),
            )
            return
        await self._show_home(update)

    async def text_message(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        if not self._is_admin(update):
            await self._reply_forbidden(update)
            return
        message = update.effective_message
        if message is None or message.text is None:
            return

        input_mode = context.user_data.get("input_mode")
        if input_mode == "profile_name":
            await self._create_profile(message, context, message.text)
            return
        if input_mode == "profile_suffix":
            await self._set_suffix_from_message(message, context, message.text)
            return

        if message.text == CREATE_PROFILE_BUTTON:
            await self._begin_profile_creation(message, context)
        elif message.text == PROFILES_BUTTON:
            await self._show_profiles(message)
        elif message.text == STATUS_BUTTON:
            await self._show_status(message)
        elif message.text == SETTINGS_BUTTON:
            await self._show_settings(message)
        else:
            await message.reply_text(
                "Выберите действие кнопкой ниже.",
                reply_markup=main_menu_keyboard(),
            )

    async def callback_query(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        query = update.callback_query
        if query is None:
            return
        if not self._is_admin(update):
            await self._reply_forbidden(update)
            return
        await query.answer()
        data = query.data if isinstance(query.data, str) else ""

        try:
            if data.startswith("setup:protocol:"):
                await self._select_setup_protocol(query, context, data.rsplit(":", 1)[1])
            elif data.startswith("setup:confirm:"):
                await self._confirm_setup(query, context, data.rsplit(":", 1)[1])
            elif data == "setup:back":
                await query.edit_message_text(
                    "Выберите один протокол:",
                    reply_markup=setup_protocol_keyboard(),
                )
            elif data == "profiles:refresh":
                if query.message is not None:
                    await self._show_profiles(query.message)
            elif data.startswith("profile:download:"):
                await self._download_profile(query, data.rsplit(":", 1)[1])
            elif data.startswith("profile:revoke:"):
                await self._request_profile_revoke(query, data.rsplit(":", 1)[1])
            elif data.startswith("profile:confirm:"):
                await self._confirm_profile_revoke(query, data.rsplit(":", 1)[1])
            elif data == "profile:cancel":
                await query.edit_message_text("Отзыв доступа отменён.")
            elif data == "settings:suffix":
                context.user_data["input_mode"] = "profile_suffix"
                if query.message is not None:
                    await query.message.reply_text(
                        "Введите суффикс без пробелов, например: prague"
                    )
            elif data == "settings:suffix:clear":
                self.update_profile_suffix("")
                await query.edit_message_text("Суффикс очищен.")
            elif data == "shutdown:request":
                await query.edit_message_text(
                    "Будут удалены VPN-сервер, центр сертификации и все сертификаты. "
                    "Скачанные конфиги перестанут работать.",
                    reply_markup=shutdown_confirmation_keyboard(),
                )
            elif data == "shutdown:confirm":
                await self._confirm_shutdown(query)
            elif data == "shutdown:cancel":
                await query.edit_message_text("Удаление отменено.")
            else:
                await query.edit_message_text("Кнопка устарела. Откройте меню заново.")
        except Exception as error:
            if query.message is not None:
                await query.message.reply_text(f"Ошибка: {error}")

    async def _select_setup_protocol(
        self,
        query: object,
        context: ContextTypes.DEFAULT_TYPE,
        protocol: str,
    ) -> None:
        if protocol not in PROTOCOL_PORTS:
            raise ValueError("Неизвестный протокол")
        public_host = await self.public_ip_detector()
        context.user_data["setup_protocol"] = protocol
        context.user_data["setup_host"] = public_host
        await query.edit_message_text(
            f"Будет запущен {protocol.upper()}-сервер:\n"
            f"адрес: {public_host}\nпорт: {PROTOCOL_PORTS[protocol]}",
            reply_markup=setup_confirmation_keyboard(protocol),
        )

    async def _confirm_setup(
        self,
        query: object,
        context: ContextTypes.DEFAULT_TYPE,
        protocol: str,
    ) -> None:
        pending_protocol = context.user_data.get("setup_protocol")
        public_host = context.user_data.get("setup_host")
        if pending_protocol != protocol or not isinstance(public_host, str):
            raise RuntimeError("Настройка устарела. Выберите протокол ещё раз.")
        await query.edit_message_text("Инициализирую OpenVPN…")
        await self.logic.command_init(protocol, public_host)
        self.state = replace(
            self.state,
            server_protocol=protocol,
            public_host=public_host,
            server_port=PROTOCOL_PORTS[protocol],
        )
        self.state_store.save(self.state)
        context.user_data.pop("setup_protocol", None)
        context.user_data.pop("setup_host", None)
        await query.edit_message_text(
            f"VPN запущен: {protocol.upper()} {public_host}:{PROTOCOL_PORTS[protocol]}"
        )
        if query.message is not None:
            await query.message.reply_text(
                "Главное меню",
                reply_markup=main_menu_keyboard(),
            )

    async def _begin_profile_creation(
        self,
        message: Message,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        if not self.state.is_initialized:
            await message.reply_text(
                "Сначала настройте VPN.",
                reply_markup=setup_protocol_keyboard(),
            )
            return
        context.user_data["input_mode"] = "profile_name"
        await message.reply_text(
            "Введите короткое имя устройства латиницей, например: iphone"
        )

    async def _create_profile(
        self,
        message: Message,
        context: ContextTypes.DEFAULT_TYPE,
        raw_profile_name: str,
    ) -> None:
        protocol = self.state.server_protocol
        if protocol is None:
            raise RuntimeError("VPN ещё не настроен")
        try:
            profile_name = normalize_profile_name(raw_profile_name)
            config_data = await self.logic.command_generate(profile_name, protocol)
        except Exception as error:
            await message.reply_text(f"Не удалось создать конфиг: {error}")
            return

        context.user_data.pop("input_mode", None)
        filename = build_profile_filename(
            profile_name,
            self.state.profile_suffix,
            protocol,
        )
        await self._send_profile_document(message, config_data, filename)

    async def _send_profile_document(
        self,
        message: Message,
        config_data: bytes,
        filename: str,
    ) -> None:
        upload_stream = BytesIO(config_data)
        upload_stream.name = filename
        await message.reply_document(
            document=InputFile(upload_stream, filename=filename),
            caption="Конфигурация готова. Храните её как пароль.",
        )

    async def _show_profiles(self, message: Message) -> None:
        if not self.state.is_initialized:
            await message.reply_text("VPN ещё не настроен.")
            return
        try:
            users = await self.logic.list_users()
        except Exception as error:
            await message.reply_text(f"Не удалось получить конфиги: {error}")
            return
        if not users:
            await message.reply_text(
                "Активных конфигов пока нет.",
                reply_markup=main_menu_keyboard(),
            )
            return
        lines = ["Активные конфиги:"]
        for user in users:
            lines.append(
                f"• {user.base_name} — {user.protocol.upper()} — действует с {user.activated_at}"
            )
        await message.reply_text(
            "\n".join(lines),
            reply_markup=profile_actions_keyboard(users),
        )

    async def _resolve_profile(self, token: str) -> UserCertificateInfo:
        users = await self.logic.list_users()
        for user in users:
            if profile_token(user.common_name) == token:
                return user
        raise RuntimeError("Конфиг не найден. Обновите список.")

    async def _download_profile(self, query: object, token: str) -> None:
        user = await self._resolve_profile(token)
        protocol = user.protocol
        if protocol not in PROTOCOL_PORTS:
            raise RuntimeError("У старого сертификата не определён протокол")
        config_data = await self.logic.command_get_profile(user.common_name, protocol)
        filename = build_profile_filename(
            user.base_name,
            self.state.profile_suffix,
            protocol,
        )
        if query.message is not None:
            await self._send_profile_document(query.message, config_data, filename)

    async def _request_profile_revoke(self, query: object, token: str) -> None:
        user = await self._resolve_profile(token)
        await query.edit_message_text(
            f"Отозвать доступ для {user.base_name}? Скачанный файл перестанет работать.",
            reply_markup=profile_revoke_confirmation_keyboard(token),
        )

    async def _confirm_profile_revoke(self, query: object, token: str) -> None:
        user = await self._resolve_profile(token)
        await self.logic.command_revoke_common_name(user.common_name)
        await query.edit_message_text(f"Доступ для {user.base_name} отозван.")

    def update_profile_suffix(self, raw_suffix: str) -> RuntimeState:
        normalized_suffix = normalize_profile_suffix(raw_suffix)
        updated_state = replace(self.state, profile_suffix=normalized_suffix)
        self.state_store.save(updated_state)
        self.state = updated_state
        return updated_state

    async def _set_suffix_from_message(
        self,
        message: Message,
        context: ContextTypes.DEFAULT_TYPE,
        raw_suffix: str,
    ) -> None:
        try:
            updated = self.update_profile_suffix(raw_suffix)
        except ValueError as error:
            await message.reply_text(f"Некорректный суффикс: {error}")
            return
        context.user_data.pop("input_mode", None)
        await message.reply_text(
            f"Суффикс сохранён: {updated.profile_suffix}",
            reply_markup=main_menu_keyboard(),
        )

    async def _show_status(self, message: Message) -> None:
        if not self.state.is_initialized:
            await message.reply_text("VPN ещё не настроен.")
            return
        try:
            docker_status = await self.logic.command_status()
        except Exception as error:
            await message.reply_text(f"Не удалось получить статус: {error}")
            return
        await self._send_text_chunks(
            message,
            f"Протокол: {self.state.server_protocol.upper()}\n"
            f"Адрес: {self.state.public_host}:{self.state.server_port}\n\n"
            f"{docker_status}",
            reply_markup=main_menu_keyboard(),
        )

    async def _show_settings(self, message: Message) -> None:
        protocol = self.state.server_protocol.upper() if self.state.server_protocol else "не выбран"
        endpoint = (
            f"{self.state.public_host}:{self.state.server_port}"
            if self.state.is_initialized
            else "не настроен"
        )
        suffix = self.state.profile_suffix or "не задан"
        await message.reply_text(
            f"Протокол: {protocol}\nАдрес: {endpoint}\nСуффикс файлов: {suffix}",
            reply_markup=settings_keyboard(bool(self.state.profile_suffix)),
        )

    async def _confirm_shutdown(self, query: object) -> None:
        await query.edit_message_text("Удаляю VPN и сертификаты…")
        await self.logic.command_remove()
        self.state = RuntimeState(profile_suffix=self.state.profile_suffix)
        self.state_store.save(self.state)
        await query.edit_message_text("VPN и все сертификаты удалены.")

    async def status_command(
        self,
        update: Update,
        _context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        if not self._is_admin(update):
            await self._reply_forbidden(update)
            return
        if update.effective_message is not None:
            await self._show_status(update.effective_message)

    async def users_command(
        self,
        update: Update,
        _context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        if not self._is_admin(update):
            await self._reply_forbidden(update)
            return
        if update.effective_message is not None:
            await self._show_profiles(update.effective_message)

    async def generate_command(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        if not self._is_admin(update):
            await self._reply_forbidden(update)
            return
        if update.effective_message is not None:
            await self._begin_profile_creation(update.effective_message, context)

    async def settings_command(
        self,
        update: Update,
        _context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        if not self._is_admin(update):
            await self._reply_forbidden(update)
            return
        if update.effective_message is not None:
            await self._show_settings(update.effective_message)

    async def shutdown_command(
        self,
        update: Update,
        _context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        if not self._is_admin(update):
            await self._reply_forbidden(update)
            return
        if update.effective_message is not None:
            await update.effective_message.reply_text(
                "Удалить VPN, центр сертификации и все сертификаты?",
                reply_markup=shutdown_confirmation_keyboard(),
            )

    async def unknown_command(
        self,
        update: Update,
        _context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        if not self._is_admin(update):
            return
        await self._show_home(update)

    def run(self) -> None:
        self.application.run_polling(allowed_updates=Update.ALL_TYPES)
