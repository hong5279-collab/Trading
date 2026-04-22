from src.bot.trader import TraderBot
from src.config import Settings


def main():
    settings = Settings.from_env()
    bot = TraderBot(settings)
    try:
        bot.connect()
        bot.run_forever()
    finally:
        bot.close()


if __name__ == "__main__":
    main()
