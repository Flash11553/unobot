import re

from telegram import ParseMode, Update
from telegram.ext import CommandHandler, CallbackContext

from user_setting import UserSetting, users_collection
from levels import compute_level
from utils import send_async
from shared_vars import dispatcher
from internationalization import _, user_locale
from promotions import send_promotion


def escape_markdown_symbols(text):
    """Markdown-da problem yaratmasın deyə * və _ simvollarını escape edir."""
    return re.sub(r'([*_])', r'\\\1', text or "")

@user_locale
def help_handler(update: Update, context: CallbackContext):
    """Handler for the /help command"""
    help_text = _("🎮 UNO Oyununa Xoş Gəlmisiniz:\n"
      "\n"
      "1️⃣ Bu botu qrupunuza əlavə edin\n"
      "2️⃣ Qrupda /new yazaraq yeni oyun yaradın və ya /join ilə mövcud oyuna qoşulun\n"
      "3️⃣ Ən azı 2 oyunçu qoşulduqdan sonra /start yazaraq oyunu başladın\n"
      "4️⃣ Oyun başladıqda 🃏 kartlarınızdan birini seçmək üçün üzərinə toxunun\n"
      "\n"
      "👥 Oyuna istənilən vaxt yeni oyunçular qoşula bilər\n"
      "🚪 Oyundan çıxmaq istəyirsinizsə, /leave yazın\n"
      "⏱ Əgər bir oyunçu 120 saniyədən çox gözlənilirsə, onu /skip ilə keçə bilərsiniz\n"
      "🔔 Yeni oyun başladıqda xəbərdar olmaq üçün /notify_me yazmağı unutmayın\n"
      "\n"
      "⚙️ Statiskanızı görmək üçün:\n"
      "💎 /stats \n"
      "\n"
      "🔐 Yalnız oyun yaradıcısı üçün əmrlər:\n"
      "🚫 /close — Oyuna girişləri bağla\n"
      "✅ /open — Oyuna girişləri aç\n"
      "🛑 /stop — Oyunu dayandır\n"
      "👢 /kick — Oyunçunu çıxarmaq üçün onun mesajına cavab ver\n")

    def _send():  
      update.message.chat.send_message(  
          help_text,  
          parse_mode=ParseMode.HTML,  
          disable_web_page_preview=True,  
      )  
      send_promotion(update.effective_chat)  

    context.dispatcher.run_async(_send)

@user_locale
def modes(update: Update, context: CallbackContext):
    """Handler for the /help command"""
    modes_explanation = _("This UNO bot has four game modes: Classic, Sanic, Wild and Text.\n\n"
      " 🎻 The Classic mode uses the conventional UNO deck and there is no auto skip.\n"
      " 🚀 The Sanic mode uses the conventional UNO deck and the bot automatically skips a player if he/she takes too long to play its turn\n"
      " 🐉 The Wild mode uses a deck with more special cards, less number variety and no auto skip.\n"
      " ✍️ The Text mode uses the conventional UNO deck but instead of stickers it uses the text.\n\n"
      "To change the game mode, the GAME CREATOR has to type the bot nickname and a space, "
      "just like when playing a card, and all gamemode options should appear.")
    send_async(context.bot, update.message.chat_id, text=modes_explanation,
              parse_mode=ParseMode.HTML, disable_web_page_preview=True) 

@user_locale
def source(update: Update, context: CallbackContext):
    """Handler for the /help command"""
    source_text = _("This bot is Free Software and licensed under the AGPL. "
      "The code is available here: \n"
      "https://github.com/jh0ker/mau_mau_bot")
    attributions = _("Attributions:\n"
      'Draw icon by '
      '<a href="http://www.faithtoken.com/">Faithtoken</a>\n'
      'Pass icon by '
      '<a href="http://delapouite.com/">Delapouite</a>\n'
      "Originals available on http://game-icons.net\n"
      "Icons edited by ɳick")
 
    send_async(context.bot, update.message.chat_id, text=source_text + '\n' +  
                                             attributions,  
               parse_mode=ParseMode.HTML, disable_web_page_preview=True)

@user_locale
def news(update: Update, context: CallbackContext):
    """Handler for the /news command"""
    send_async(context.bot, update.message.chat_id,
               text=_("All news here: https://telegram.me/unobotnews"),
               disable_web_page_preview=True)

@user_locale
def profile_handler(update: Update, context: CallbackContext):
    """Handler for the /profile command - şəxsi statistika kartı"""
    user = update.message.from_user
    us = UserSetting.get(id=user.id)
    if not us or not us.stats:
        send_async(context.bot, update.message.chat_id,
                   text=_("Sizin Statistikanız hələ mövcud deyil. Statistikanı "
                          "aktivləşdirmək üçün /settings yazın və bir oyun oynayın."))
        return

    level, rank_name = compute_level(us.first_places)

    profile_text = (
        "👤 Oyunçu\n\n"
        f"🏅 Rütbə: {rank_name}\n"
        f"⭐ Səviyyə: {level}\n\n"
        f"🎮 Oyun: {us.games_played}\n"
        f"🏆 Qələbə: {us.first_places}\n"
    )

    send_async(context.bot, update.message.chat_id, text=profile_text)


@user_locale
def rating_leaderboard(update: Update, context: CallbackContext):
    """Handler for the /rating command - ən çox qələbə qazanan 25 oyunçu"""
    if users_collection is None:
        send_async(context.bot, update.message.chat_id,
                   text=_("Reytinq siyahısı hazırda əlçatan deyil."))
        return

    top = list(
        users_collection.find({"stats": True, "first_places": {"$gt": 0}})
        .sort("first_places", -1)
        .limit(25)
    )

    if not top:
        send_async(context.bot, update.message.chat_id,
                   text=_("Reytinq siyahısı hələ boşdur. Oyun oynayın və qalib gəlin!"))
        return

    rating_message = "👑 *UNO Reytinq Siyahısı:*\n\n"
    for i, doc in enumerate(top, start=1):
        name = escape_markdown_symbols(doc.get("name") or "Anonim")
        wins = doc.get("first_places", 0)
        level, rank_name = doc.get("level"), doc.get("rank_name")
        if level is None or rank_name is None:
            level, rank_name = compute_level(wins)
        rating_message += f"{i}. {name} — {rank_name} ⭐{level} — *{wins} qələbə*\n"

    send_async(context.bot, update.message.chat_id, text=rating_message,
               parse_mode=ParseMode.MARKDOWN)


def register():
    dispatcher.add_handler(CommandHandler('help', help_handler))
    dispatcher.add_handler(CommandHandler('yrjrj', source))
    dispatcher.add_handler(CommandHandler('newsdusi', news))
    dispatcher.add_handler(CommandHandler('rating', rating_leaderboard))
    dispatcher.add_handler(CommandHandler('profile', profile_handler))
    dispatcher.add_handler(CommandHandler('modesdkdk', modes))
