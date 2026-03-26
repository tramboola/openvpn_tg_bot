from __future__ import annotations

from io import BytesIO

from telegram import BotCommand, InputFile, Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from ovpn_bot.config import Settings
from ovpn_bot.docker_logic import OvpnLogic, split_long_message

HELP_TEXT = """Available commands:

/init - initialize OpenVPN
Example: /init tcp://1.2.3.4:443

/status - Docker container status

/users - list users with protocol and activation date

/generate_tcp - generate a TCP profile (more stable on restricted networks)
Example: /generate_tcp laptop

/generate_udp - generate a UDP profile (usually faster)
Example: /generate_udp laptop

/generate - compatibility alias, same as /generate_tcp

/remove_user - revoke a user certificate
Example: /remove_user laptop tcp

/shutdown - remove ovpn containers and volume completely
/help - show this message
"""


class TelegramOvpnBot:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.logic = OvpnLogic(settings.docker_bin)
        self.application = (
            Application.builder()
            .token(settings.bot_token)
            .post_init(self._post_init)
            .build()
        )
        self._register_handlers()

    async def _post_init(self, _application: Application) -> None:
        commands = [
            BotCommand("start", "Show command list"),
            BotCommand("help", "Show command list"),
            BotCommand("init", "Initialize OpenVPN"),
            BotCommand("status", "Show container status"),
            BotCommand("users", "List users and protocols"),
            BotCommand("generate_tcp", "Generate TCP .ovpn profile"),
            BotCommand("generate_udp", "Generate UDP .ovpn profile"),
            BotCommand("generate", "Generate TCP .ovpn (compatibility)"),
            BotCommand("remove_user", "Remove user by name and protocol"),
            BotCommand("shutdown", "Completely remove ovpn containers and volume"),
        ]
        await self.application.bot.set_my_commands(commands)

    def _register_handlers(self) -> None:
        self.application.add_handler(CommandHandler("start", self.help_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("init", self.init_command))
        self.application.add_handler(CommandHandler("status", self.status_command))
        self.application.add_handler(CommandHandler("users", self.users_command))
        self.application.add_handler(CommandHandler("generate_tcp", self.generate_tcp_command))
        self.application.add_handler(CommandHandler("generate_udp", self.generate_udp_command))
        self.application.add_handler(CommandHandler("generate", self.generate_command))
        self.application.add_handler(CommandHandler("remove_user", self.remove_user_command))
        self.application.add_handler(CommandHandler("shutdown", self.shutdown_command))
        self.application.add_handler(CommandHandler("remove", self.remove_alias_command))
        self.application.add_handler(MessageHandler(filters.COMMAND, self.unknown_command))

    def _is_admin(self, update: Update) -> bool:
        user = update.effective_user
        return user is not None and user.id in self.settings.admin_ids

    async def _reply_forbidden(self, update: Update) -> None:
        if update.effective_message is not None:
            await update.effective_message.reply_text("Access denied")

    async def _send_text_chunks(self, update: Update, text: str) -> None:
        if update.effective_message is None:
            return
        for chunk in split_long_message(text):
            await update.effective_message.reply_text(chunk)

    async def help_command(self, update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_admin(update):
            await self._reply_forbidden(update)
            return
        await self._send_text_chunks(update, HELP_TEXT)

    async def init_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_admin(update):
            await self._reply_forbidden(update)
            return

        address = context.args[0] if context.args else ""
        if not address:
            await self._send_text_chunks(update, "Usage: /init tcp://1.2.3.4:443")
            return
        try:
            messages = await self.logic.command_init(address)
        except Exception as error:
            await self._send_text_chunks(update, f"Error while init:\n\n{error}")
            return

        for message in messages:
            await self._send_text_chunks(update, message)

    async def status_command(self, update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_admin(update):
            await self._reply_forbidden(update)
            return
        try:
            result = await self.logic.command_status()
        except Exception as error:
            await self._send_text_chunks(update, f"Error while status:\n\n{error}")
            return
        await self._send_text_chunks(update, result)

    async def users_command(self, update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_admin(update):
            await self._reply_forbidden(update)
            return
        try:
            result = await self.logic.command_users()
        except Exception as error:
            await self._send_text_chunks(update, f"Error while users:\n\n{error}")
            return
        await self._send_text_chunks(update, result)

    async def generate_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._generate_profile(update, context, protocol="tcp")

    async def generate_tcp_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._generate_profile(update, context, protocol="tcp")

    async def generate_udp_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._generate_profile(update, context, protocol="udp")

    async def _generate_profile(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        protocol: str,
    ) -> None:
        if not self._is_admin(update):
            await self._reply_forbidden(update)
            return

        profile_name = context.args[0] if context.args else ""
        if not profile_name:
            if protocol == "udp":
                await self._send_text_chunks(update, "Usage: /generate_udp profile_name")
            else:
                await self._send_text_chunks(update, "Usage: /generate_tcp profile_name")
            return

        try:
            config_data = await self.logic.command_generate(profile_name, protocol=protocol)
        except Exception as error:
            await self._send_text_chunks(update, f"Error while generate:\n\n{error}")
            return

        if update.effective_message is None:
            return

        upload_stream = BytesIO(config_data)
        upload_stream.name = f"{profile_name}_{protocol}.ovpn"
        await update.effective_message.reply_document(document=InputFile(upload_stream))

    async def remove_command(self, update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        await self.shutdown_command(update, _context)

    async def remove_alias_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_admin(update):
            await self._reply_forbidden(update)
            return
        await self._send_text_chunks(update, "The /remove command is deprecated. Use /shutdown.")
        await self.shutdown_command(update, context)

    async def shutdown_command(self, update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_admin(update):
            await self._reply_forbidden(update)
            return
        try:
            messages = await self.logic.command_remove()
        except Exception as error:
            await self._send_text_chunks(update, f"Error while shutdown:\n\n{error}")
            return
        for message in messages:
            await self._send_text_chunks(update, message)

    async def remove_user_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_admin(update):
            await self._reply_forbidden(update)
            return
        if len(context.args) < 2:
            await self._send_text_chunks(update, "Usage: /remove_user profile_name tcp|udp")
            return

        profile_name = context.args[0]
        protocol = context.args[1]
        try:
            result = await self.logic.command_remove_user(profile_name=profile_name, protocol=protocol)
        except Exception as error:
            await self._send_text_chunks(update, f"Error while remove_user:\n\n{error}")
            return
        await self._send_text_chunks(update, result)

    async def unknown_command(self, update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_admin(update):
            return
        await self._send_text_chunks(update, HELP_TEXT)

    def run(self) -> None:
        self.application.run_polling(allowed_updates=Update.ALL_TYPES)
