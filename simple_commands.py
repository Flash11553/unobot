#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from telegram import ParseMode, Update
from telegram.ext import CommandHandler, CallbackContext

from utils import send_async
from shared_vars import dispatcher
from internationalization import _, user_locale
from promotions import send_promotion

# =======================
# MongoDB
# =======================
from pony.orm import db_session, desc
from models import UserSetting


# =======================
# HELP
# =======================
@user_locale
def help_handler(update: Update, context: CallbackContext):
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
                  "⚙️ Statistika:\n"
                  "🏆 /stats — TOP 25 oyunçu\n")

    def _send():
        update.message.chat.send_message(
            help_text,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
        send_promotion(update.effective_chat)

    context.dispatcher.run_async(_send)


# =======================
# MODES
# =======================
@user_locale
def modes(update: Update, context: CallbackContext):
    modes_explanation = _("This UNO bot has four game modes: Classic, Sanic, Wild and Text.\n\n"
                          " 🎻 Classic — normal UNO\n"
                          " 🚀 Sanic — auto skip\n"
                          " 🐉 Wild — more special cards\n"
                          " ✍️ Text — text cards\n")
    send_async(
        context.bot,
        update.message.chat_id,
        text=modes_explanation,
        parse_mode=ParseMode.HTML
    )


# =======================
# SOURCE
# =======================
@user_locale
def source(update: Update, context: CallbackContext):
    send_async(
        context.bot,
        update.message.chat_id,
        text=_("Source code:\nhttps://github.com/jh0ker/mau_mau_bot"),
        disable_web_page_preview=True
    )


# =======================
# NEWS
# =======================
@user_locale
def news(update: Update, context: CallbackContext):
    send_async(
        context.bot,
        update.message.chat_id,
        text=_("All news here: https://telegram.me/unobotnews"),
        disable_web_page_preview=True
    )


# =======================
# STATS → TOP 25
# =======================
@user_locale
@db_session
def stats(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id

    users = (
        UserSetting
        .select(lambda u: u.first_places > 0 and u.stats == True)
        .order_by(lambda u: desc(u.first_places))
        [:25]
    )

    if not users:
        send_async(
            context.bot,
            chat_id,
            text=_("Hələ statistika mövcud deyil.")
        )
        return

    lines = ["🏆 TOP 25 — Ən çox qələbə qazanan oyunçular\n"]

    for i, user in enumerate(users, start=1):
        lines.append(
            f"{i}. ID:{user.id} — 🥇 {user.first_places} qələbə ({user.games_played} oyun)"
        )

    send_async(
        context.bot,
        chat_id,
        text="\n".join(lines)
    )


# =======================
# REGISTER
# =======================
def register():
    dispatcher.add_handler(CommandHandler('help', help_handler))
    dispatcher.add_handler(CommandHandler('stats', stats))
    dispatcher.add_handler(CommandHandler('newsdusi', news))
    dispatcher.add_handler(CommandHandler('yrjrj', source))
    dispatcher.add_handler(CommandHandler('modesdkdk', modes))
