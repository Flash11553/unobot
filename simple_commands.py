import re

from telegram import ParseMode, Update
from telegram.ext import CommandHandler, CallbackContext

from user_setting import UserSetting, users_collection
from levels import compute_level, LEVELS
from utils import send_async
from shared_vars import dispatcher
from internationalization import _, user_locale
from promotions import send_promotion
from broadcast_store import add_served_chat, add_served_user


def escape_markdown_symbols(text):
    """Markdown-da problem yaratmasın deyə * və _ simvollarını escape edir."""
    return re.sub(r'([*_])', r'\\\1', text or "")

@user_locale
def help_handler(update: Update, context: CallbackContext):
    """Handler for the /help command"""
    chat = update.effective_chat
    user = update.effective_user
    if chat is not None:
        if chat.type == 'private':
            if user:
                add_served_user(user.id)
        else:
            add_served_chat(chat.id)
            if user:
                add_served_user(user.id)

    help_text = _("🎮 UNO Oyununa Xoş Gəlmisiniz:\n"
      "\n"
      "1️⃣ Bu botu qrupunuza əlavə edin\n"
      "2️⃣ Qrupda /uno yazaraq yeni oyun yaradın və ya \"Oyuna Qoşul\"(/join) düyməsi ilə mövcud oyuna qoşulun\n"
      "3️⃣ Ən azı 2 oyunçu qoşulduqdan sonra \"Oyunu Başlat\"(/start) düyməsi ilə oyunu başladın\n"
      "4️⃣ Oyun başladıqda 🃏 kartlarınızdan birini seçmək üçün \"Seçiminizi Edin\" üzərinə toxunun\n"
      "\n"
      "👥 Oyuna istənilən vaxt yeni oyunçular qoşula bilər\n"
      "🚪 Oyundan çıxmaq istəyirsinizsə, /leave yazın\n"
      "⏭️ Oyunçunu keçmək istəyirsinizsə, /skip yazın\n"
      "\n"
      "⚙️ Statistikanızı görmək üçün:\n"
      "💎 /profile — şəxsi statistikanız\n"
      "🏆 /rating — top 25 reytinq siyahısı\n"
      "🎖 /rutbeler — səviyyə və rütbələr haqqında\n"
      "\n"
      "🔐 Yalnız qrupda oyunu başladan üçün əmrlər:\n"
      "🚫 /close — Oyuna girişləri bağla\n"
      "✅ /open — Oyuna girişləri aç\n"
      "🛑 /stop — Oyunu dayandır\n")

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

    games_played = int(getattr(us, "games_played", 0) or 0) if us else 0
    first_places = int(getattr(us, "first_places", 0) or 0) if us else 0

    if games_played == 0:
        send_async(context.bot, update.message.chat_id,
                   text=_("Siz hələ heç bir oyun oynamamısınız. Əvvəlcə ən azından bir oyun oynayın qrupda dostlarnızla: /uno yazaraq oyun başladın!"))
        return

    level, rank_name = compute_level(first_places)

    profile_text = (
        f"👤 {user.first_name}\n\n"
        f"🏅 Rütbə: {rank_name}\n"
        f"⭐ Səviyyə: {level}\n\n"
        f"🎮 Oyun: {games_played}\n"
        f"🏆 Qələbə: {first_places}\n"
    )

    send_async(context.bot, update.message.chat_id, text=profile_text)


@user_locale
def rating_leaderboard(update: Update, context: CallbackContext):
    """Handler for the /rating command - ən çox qələbə qazanan 25 oyunçu"""
    if users_collection is None:
        send_async(context.bot, update.message.chat_id,
                   text=_("Reytinq siyahısı hazırda əlçatan deyil."))
        return

    try:
        docs = list(users_collection.find({}).sort("first_places", -1).limit(100))
    except Exception:
        send_async(context.bot, update.message.chat_id,
                   text=_("Reytinq siyahısı hazırda əlçatan deyil."))
        return

    top = [d for d in docs if int(d.get("first_places", 0) or 0) > 0][:25]

    if not top:
        send_async(context.bot, update.message.chat_id,
                   text=_("Reytinq siyahısı hələ boşdur. Oyun oynayın və qalib gəlin!"))
        return

    rating_message = "👑 *UNO Reytinq Siyahısı:*\n\n"
    for i, doc in enumerate(top, start=1):
        name = escape_markdown_symbols(doc.get("name") or "Anonim")
        wins = int(doc.get("first_places", 0) or 0)
        level, rank_name = compute_level(wins)
        rating_message += f"{i}. {name} — {rank_name} ⭐{level} — *{wins} qələbə*\n"

    send_async(context.bot, update.message.chat_id, text=rating_message,
               parse_mode=ParseMode.MARKDOWN)


@user_locale
def ranks_handler(update: Update, context: CallbackContext):
    """Handler for the /rutbeler command - səviyyə/rütbə sistemini izah edir"""
    lines = ["🎖 *Səviyyə və Rütbələr*\n",
             "Hər dəfə oyunçu oyunu 1-ci yerdə bitirdikcə (qalib gəldikcə) "
             "xalınız (qələbə sayınız) 1 artır. Qələbə sayınız artdıqca "
             "səviyyəniz və rütbəniz avtomatik yüksəlir:\n"]

    for i, (threshold, level, rank_name) in enumerate(LEVELS):
        if i + 1 < len(LEVELS):
            next_threshold = LEVELS[i + 1][0]
            lines.append(f"⭐ Səviyyə {level} — {rank_name}: {threshold}-{next_threshold - 1} qələbə")
        else:
            lines.append(f"⭐ Səviyyə {level} — {rank_name}: {threshold}+ qələbə")

    lines.append("\nHamı 1-ci səviyyədən (🔰 Yeni Başlayan) başlayır. "
                 "Öz statistikanızı /profile, top 25 reytinqi isə /rating "
                 "əmri ilə görə bilərsiniz.")

    send_async(context.bot, update.message.chat_id, text="\n".join(lines),
               parse_mode=ParseMode.MARKDOWN)


def register():
    dispatcher.add_handler(CommandHandler('help', help_handler))
    dispatcher.add_handler(CommandHandler('yrjrj', source))
    dispatcher.add_handler(CommandHandler('newsdusi', news))
    dispatcher.add_handler(CommandHandler('rating', rating_leaderboard))
    dispatcher.add_handler(CommandHandler('profile', profile_handler))
    dispatcher.add_handler(CommandHandler('rutbeler', ranks_handler))
    dispatcher.add_handler(CommandHandler('modesdkdk', modes))
