import os
from telegram.ext import Updater

def start_bot(updater):
    updater.start_polling()

def main():
    TOKEN = os.environ.get("TOKEN")
    updater = Updater(token=TOKEN, use_context=True)
    start_bot(updater)
    updater.idle()  # Botu işlək saxlayır

if __name__ == "__main__":
    main()
