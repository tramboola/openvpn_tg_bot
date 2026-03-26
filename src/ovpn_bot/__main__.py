from __future__ import annotations

from dotenv import load_dotenv

from ovpn_bot.config import load_settings
from ovpn_bot.telegram_bot import TelegramOvpnBot


def main() -> None:
    load_dotenv()
    settings = load_settings()
    bot = TelegramOvpnBot(settings)
    bot.run()


if __name__ == "__main__":
    main()

