from telegram.ext import Updater, CommandHandler

TOKEN = "SENIN_BOT_TOKENIN"

def start(update, context):
    update.message.reply_text("Salam! Mən Heroku üzərində işləyən sadə botam.")

def main():
    updater = Updater(TOKEN, use_context=True)

    dp = updater.dispatcher
    dp.add_handler(CommandHandler("start", start))

    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
