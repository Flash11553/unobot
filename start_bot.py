import os
import gettext
from telegram.ext import Updater
from unobot import UnoBot  # əsas UNO oyun klası

def main():
    # TOKEN Heroku environment-dan alınır
    TOKEN = os.environ.get("TOKEN")
    if not TOKEN:
        print("❌ Telegram bot token tapılmadı. TOKEN env dəyişəni təyin olunmalıdır.")
        return

    # Dil sistemini aktivləşdir
    lang = os.environ.get("LANG", "en")
    locales_path = os.path.join(os.path.dirname(__file__), "locales")

    try:
        translation = gettext.translation("unobot", locales_path, languages=[lang])
        translation.install()
    except FileNotFoundError:
        print("⚠️ Dil faylı tapılmadı, default gettext istifadə ediləcək.")
        gettext.install("unobot")

    # Botu başlat
    updater = Updater(token=TOKEN, use_context=True)

    # UNO bot obyektini yaradıb handler-ları əlavə et
    UnoBot(updater)

    print("✅ UNO Bot başladı!")
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
