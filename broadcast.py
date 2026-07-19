#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Domino botundakı /broadcast məntiqinin UNO botuna uyğunlaşdırılmış versiyası:
#   - Hər mesajda (hansı əmr olur olsun) qrup/istifadəçi səssizcə Mongo-ya yazılır
#   - Bot qrupa əlavə olunan kimi (heç bir əmr işlədilməsə belə) o qrup dərhal yazılır
#   - /broadcast reply olunan mesajı bütün saxlanılan qrup+şəxslərə forward edir
#   - Heç nə Mongo-dan silinmir (bot restart olsa belə)

import logging
import threading
import time

from telegram import Update
from telegram.error import RetryAfter, Unauthorized, BadRequest, TelegramError
from telegram.ext import CommandHandler, MessageHandler, Filters, CallbackContext

from config import SUDO_USERS
from shared_vars import dispatcher
from broadcast_store import (
    add_served_chat, add_served_user, get_served_chats, get_served_users,
    _log_broadcast_error,
)

logger = logging.getLogger(__name__)


def track_activity(update: Update, context: CallbackContext):
    """Hər mesajda (hansı əmr/mətn olur olsun - /start, /uno, /new, /help və s.
    daxil olmaqla) qrupu/istifadəçini səssizcə Mongo-ya yazır. Digər
    handler-lərdən tamamilə ayrı (group=99) işlədiyi üçün heç birinin
    məntiqinə toxunmur."""
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
    except Exception as e:
        logger.error(f"track_activity xətası: {e}")


def new_member_handler(update: Update, context: CallbackContext):
    """Bot qrupa əlavə olunan kimi (heç bir əmr gözləmədən) o qrupu
    dərhal /broadcast siyahısına (Mongo) yazır."""
    try:
        new_members = update.message.new_chat_members or []
        if context.bot.id in [u.id for u in new_members]:
            add_served_chat(update.message.chat.id)
    except Exception as e:
        logger.error(f"new_member_handler xətası: {e}")


def _forward_to_target(bot, target_id, source_chat_id, source_message_id, kind):
    """Bir qrup/istifadəçiyə mesajı YALNIZ BİR DƏFƏ göndərməyə cəhd edir.
    QƏSDƏN heç bir təkrar (retry) cəhd EDİLMİR - çünki RetryAfter xətasından
    sonra ikinci cəhd bəzən eyni şəxsə mesajın İKİ DƏFƏ getməsinə səbəb
    olurdu. Rate-limit-ə düşən hədəf sadəcə "uğursuz" sayılır, təkrar
    göndərilmir.
    Return: 'sent' | 'blocked' | 'failed'"""
    try:
        bot.forward_message(target_id, source_chat_id, source_message_id)
        return "sent"
    except RetryAfter as e:
        _log_broadcast_error(kind, target_id, f"RetryAfter: {e.retry_after}s (təkrar cəhd edilmədi)")
        return "failed"
    except Unauthorized as e:
        # İstifadəçi botu bloklayıb, botu silib, ya da botla HEÇ VAXT şəxsi
        # (/start) əlaqəyə keçməyib - Telegram-ın özü bu mesajı ötürməyə
        # icazə vermir (platform məhdudiyyəti, koddan düzəldilə bilməz).
        _log_broadcast_error(kind, target_id, f"Unauthorized: {e}")
        return "blocked"
    except BadRequest as e:
        _log_broadcast_error(kind, target_id, f"BadRequest: {e}")
        return "failed"
    except TelegramError as e:
        _log_broadcast_error(kind, target_id, f"TelegramError: {e}")
        return "failed"
    except Exception as e:
        _log_broadcast_error(kind, target_id, str(e))
        return "failed"


def _run_broadcast(bot, source_chat_id, source_message_id, status_msg, fallback_msg):
    """Reklamın faktiki göndərilməsi - bu, ayrıca arxa fon thread-də işləyir
    ki, botun əsas dispatcher-i (oyun, digər əmrlər) HEÇ VAXT bloklanmasın."""
    served_chats = get_served_chats()
    served_users = get_served_users()

    logger.info(f"/broadcast başladı: {len(served_chats)} qrup, {len(served_users)} istifadəçi qeydə alınıb.")

    sent_chats = failed_chats = 0
    for chat in served_chats:
        try:
            chat_id = chat["chat_id"]
            result = _forward_to_target(bot, chat_id, source_chat_id, source_message_id, "chat")
            if result == "sent":
                sent_chats += 1
            else:
                failed_chats += 1
            time.sleep(0.3)
        except Exception as e:
            logger.error(f"Qrup emalı zamanı gözlənilməz xəta ({chat}): {e}")
            failed_chats += 1

    sent_users = blocked_users = failed_users = 0
    for u in served_users:
        try:
            uid = u["user_id"]
            result = _forward_to_target(bot, uid, source_chat_id, source_message_id, "user")
            if result == "sent":
                sent_users += 1
            elif result == "blocked":
                blocked_users += 1
            else:
                failed_users += 1
            time.sleep(0.3)
        except Exception as e:
            logger.error(f"İstifadəçi emalı zamanı gözlənilməz xəta ({u}): {e}")
            failed_users += 1

    summary = (
        f"✅ *Reklam prosesi bitdi!*\n\n"
        f"👥 *Qruplar* (cəmi {len(served_chats)}):\n"
        f"   ✔️ Uğurlu: {sent_chats}\n"
        f"   ❌ Uğursuz: {failed_chats}\n\n"
        f"👤 *İstifadəçilər* (cəmi {len(served_users)}):\n"
        f"   ✔️ Uğurlu: {sent_users}\n"
        f"   🚫 Bloklayıb / botu heç vaxt başlatmayıb: {blocked_users}\n"
        f"   ❌ Digər xəta: {failed_users}\n"
    )

    logger.info(
        f"/broadcast bitdi: qruplar {sent_chats}/{len(served_chats)} uğurlu, "
        f"istifadəçilər {sent_users}/{len(served_users)} uğurlu "
        f"({blocked_users} bloklanıb, {failed_users} digər xəta)."
    )

    try:
        status_msg.edit_text(summary, parse_mode="Markdown")
    except Exception:
        try:
            fallback_msg.reply_text(summary, parse_mode="Markdown")
        except Exception as e:
            logger.error(f"/broadcast yekun hesabatı göndərilə bilmədi: {e}")


def broadcast_command(update: Update, context: CallbackContext):
    """Handler for the /broadcast command. Faktiki göndərmə işini arxa fon
    thread-inə ötürür və DƏRHAL geri qayıdır - bu sayədə /broadcast davam
    edərkən botun özü (oyun, digər əmrlər) heç vaxt donmur/bloklanmır."""
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

    thread = threading.Thread(
        target=_run_broadcast,
        args=(bot, source_chat_id, source_message_id, status_msg, msg),
        daemon=True,
    )
    thread.start()


def register():
    # group=99: digər handler-lərdən tamamilə ayrı, paralel işləyir, heç
    # birinin məntiqinə mane olmur (bax: PTB "groups" mexanizmi)
    dispatcher.add_handler(MessageHandler(Filters.all, track_activity), group=99)
    dispatcher.add_handler(
        MessageHandler(Filters.status_update.new_chat_members, new_member_handler),
        group=99,
    )
    dispatcher.add_handler(CommandHandler("broadcast", broadcast_command))
