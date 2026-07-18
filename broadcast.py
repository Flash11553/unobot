#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Domino botundakı /broadcast məntiqinin UNO botuna uyğunlaşdırılmış versiyası:
#   - Hər mesajda (hansı əmr olur olsun) qrup/istifadəçi səssizcə Mongo-ya yazılır
#   - Bot qrupa əlavə olunan kimi (heç bir əmr işlədilməsə belə) o qrup dərhal yazılır
#   - /broadcast reply olunan mesajı bütün saxlanılan qrup+şəxslərə forward edir
#   - Heç nə Mongo-dan silinmir (bot restart olsa belə)

import logging
import time

from telegram import Update
from telegram.error import RetryAfter
from telegram.ext import CommandHandler, MessageHandler, Filters, CallbackContext

from config import SUDO_USERS
from shared_vars import dispatcher
from broadcast_store import (
    add_served_chat, add_served_user, get_served_chats, get_served_users,
    _log_broadcast_error,
)

logger = logging.getLogger(__name__)


def track_activity(update: Update, context: CallbackContext):
    """Hər mesajda (digər handler-lərin işinə mane olmadan, ayrı group-da)
    qrupu/istifadəçini səssizcə Mongo-ya yazır."""
    try:
        message = update.effective_message
        chat = update.effective_chat
        user = update.effective_user
        if not message or not chat:
            return

        if chat.type == "private":
            if user:
                add_served_user(user.id)
        else:
            add_served_chat(chat.id)
            if user:
                add_served_user(user.id)
    except Exception:
        pass


def new_member_handler(update: Update, context: CallbackContext):
    """Bot qrupa əlavə olunan kimi (heç bir əmr gözləmədən) o qrupu
    dərhal /broadcast siyahısına (Mongo) yazır."""
    try:
        new_members = update.message.new_chat_members or []
        if context.bot.id in [u.id for u in new_members]:
            add_served_chat(update.message.chat.id)
    except Exception:
        pass


def broadcast_command(update: Update, context: CallbackContext):
    """Handler for the /broadcast command"""
    msg = update.message
    bot = context.bot

    if str(msg.from_user.id) not in SUDO_USERS:
        msg.reply_text("⛔ Bu əmr yalnız adminlər üçündür.")
        return

    if not msg.reply_to_message:
        msg.reply_text(
            "✍️ Yaymaq istədiyin mesaja (reklam, kanal postu, şəkil - nə olursa) "
            "REPLY edərək /broadcast yaz."
        )
        return

    source_chat_id = msg.chat.id
    source_message_id = msg.reply_to_message.message_id

    status_msg = msg.reply_text("⚡ Reklam prosesi başladı, gözlə...")

    sent_chats, failed_chats = 0, 0
    for chat in get_served_chats():
        chat_id = chat["_id"]
        try:
            bot.forward_message(chat_id, source_chat_id, source_message_id)
            sent_chats += 1
            time.sleep(0.3)
        except RetryAfter as e:
            if e.retry_after > 200:
                failed_chats += 1
                continue
            time.sleep(e.retry_after)
            try:
                bot.forward_message(chat_id, source_chat_id, source_message_id)
                sent_chats += 1
            except Exception as ex:
                _log_broadcast_error("chat", chat_id, str(ex))
                failed_chats += 1
        except Exception as e:
            _log_broadcast_error("chat", chat_id, str(e))
            failed_chats += 1

    sent_users, failed_users = 0, 0
    for u in get_served_users():
        uid = u["_id"]
        try:
            bot.forward_message(uid, source_chat_id, source_message_id)
            sent_users += 1
            time.sleep(0.3)
        except RetryAfter as e:
            if e.retry_after > 200:
                failed_users += 1
                continue
            time.sleep(e.retry_after)
            try:
                bot.forward_message(uid, source_chat_id, source_message_id)
                sent_users += 1
            except Exception as ex:
                _log_broadcast_error("user", uid, str(ex))
                failed_users += 1
        except Exception as e:
            _log_broadcast_error("user", uid, str(e))
            failed_users += 1

    summary = (
        f"✅ Reklam prosesi bitdi!\n\n"
        f"👥 Qruplar: {sent_chats} uğurlu, {failed_chats} uğursuz\n"
        f"👤 İstifadəçilər: {sent_users} uğurlu, {failed_users} uğursuz"
    )
    try:
        status_msg.edit_text(summary)
    except Exception:
        msg.reply_text(summary)


def register():
    # group=99: digər handler-lərdən tamamilə ayrı, paralel işləyir, heç
    # birinin məntiqinə mane olmur (bax: PTB "groups" mexanizmi)
    dispatcher.add_handler(MessageHandler(Filters.all, track_activity), group=99)
    dispatcher.add_handler(
        MessageHandler(Filters.status_update.new_chat_members, new_member_handler),
        group=99,
    )
    dispatcher.add_handler(CommandHandler("broadcast", broadcast_command))
