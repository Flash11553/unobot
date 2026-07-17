#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
UNO Bot — Əsas Handler Faylı
Ehtiva edir:
  • /new, /uno  — Domino stilli qeydiyyat menyusu (inline düymələrlə)
  • /join       — Mövcud lobbiyə qoşulma
  • /start      — Oyunu başlatma (≥2 oyunçu)
  • /leave      — Oyundan çıxma
  • /kick       — Oyunçunu çıxarma (yaradıcı/admin)
  • /close /open — Lobbini bağla/aç
  • /stop       — Oyunu dayandır
  • /skip       — Növbəni keç (vaxt aşımı)
  • /notify_me  — Yeni oyun bildirişi
  • /broadcast  — Bütün qrup+istifadəçilərə mesaj (sudo)
  • /profile    — Oyunçu statistikası
  • /rating     — Top 25 siyahısı
  • Inline kart oynama məntiqi
  • Oyun sonu: tam sıralama (1→N), xal+səviyyə sistemi, MongoDB saxlama
"""

import logging
import time
from datetime import datetime

from telegram import (
    Update, ParseMode, InlineKeyboardMarkup, InlineKeyboardButton,
    InlineQueryResultArticle, InputTextMessageContent,
    InlineQueryResultCachedSticker as Sticker,
)
from telegram.ext import (
    Updater, CommandHandler, InlineQueryHandler, ChosenInlineResultHandler,
    CallbackQueryHandler, MessageHandler, Filters, CallbackContext,
)
from telegram.error import TelegramError, Unauthorized, BadRequest
from pony.orm import db_session

import card as c
from config import (
    TOKEN, WORKERS, MIN_PLAYERS, MAX_PLAYERS,
    SUDO_USERS, get_rank, PLACE_POINTS,
)
from mongo_db import (
    add_served_chat, add_served_user, get_served_chats, get_served_users,
    log_broadcast_error, record_game_result, get_profile, get_top_ratings,
)
from shared_vars import gm, updater, dispatcher
from game_manager import GameManager
from errors import (
    AlreadyJoinedError, LobbyClosedError, NoGameInChatError,
    NotEnoughPlayersError,
)
from utils import (
    display_name, display_color, display_color_group,
    user_is_creator_or_admin, user_is_creator,
)
from results import (
    add_card, add_draw, add_gameinfo, add_other_cards, add_pass,
    add_call_bluff, add_choose_color, add_no_game, add_not_started,
    add_mode_classic, add_mode_fast, add_mode_wild, add_mode_text,
)
from internationalization import _, __, user_locale, game_locales
from user_setting import UserSetting
from promotions import send_promotion

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ─── Qeydiyyat menyusu üçün gözləyən bildiriş istifadəçiləri ────────────────
remind_dict = {}      # chat_id → set of user_ids


# ════════════════════════════════════════════════════════════════════════════════
# KÖMƏKÇİ FUNKSİYALAR
# ════════════════════════════════════════════════════════════════════════════════

def _rank_tag(user_id: int) -> str:
    """Oyunçunun qısa səviyyə+ad etiketini qaytarır, məs. [⭐6 Usta]"""
    prof = get_profile(user_id)
    if not prof:
        return "[🌱1 Yeni Başlayan]"
    level, rank_name, rank_emoji = get_rank(prof.get("total_points", 0))
    return f"[{rank_emoji}{level} {rank_name}]"


def _lobby_text(game) -> str:
    """Qeydiyyat mesajının mətnini qaytarır."""
    player_lines = []
    for i, player in enumerate(game.players, 1):
        tag = _rank_tag(player.user.id)
        name = display_name(player.user)
        player_lines.append(f"  {i}. {name} {tag}")

    count = len(game.players)
    players_str = "\n".join(player_lines) if player_lines else "  _(hələ kimsə qoşulmayıb)_"

    status = ""
    if not game.open:
        status = "\n🔒 *Qeydiyyat bağlıdır*"

    return (
        f"🃏 *UNO Oyununa Qeydiyyat Başladı!*\n\n"
        f"*Qoşulanlar ({count}/{MAX_PLAYERS} nəfər):*\n"
        f"{players_str}\n\n"
        f"_(Oyunun başlanması üçün ən az {MIN_PLAYERS} nəfər lazımdır)_"
        f"{status}"
    )


def _lobby_keyboard(game) -> InlineKeyboardMarkup:
    """Qeydiyyat menyusunun düymələrini qaytarır."""
    buttons = [[InlineKeyboardButton("🙋 Oyuna Qoşul", callback_data="uno_join")]]
    if len(game.players) >= MIN_PLAYERS:
        buttons[0].append(InlineKeyboardButton("▶️ Oyunu Başlat", callback_data="uno_start"))
    return InlineKeyboardMarkup(buttons)


def _update_lobby_message(context: CallbackContext, chat_id: int, message_id: int, game):
    """Qeydiyyat mesajını yeniləyir."""
    try:
        context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=_lobby_text(game),
            reply_markup=_lobby_keyboard(game),
            parse_mode=ParseMode.MARKDOWN,
        )
    except Exception:
        pass


def _announce_results(context: CallbackContext, chat_id: int, finish_order: list):
    """
    Oyun bitdikdən sonra tam sıralama mesajını göndərir.
    finish_order: [(place, user, cards_left), ...]  — bitirmə sırasına görə
    """
    PLACE_EMOJIS = {1: "🥇", 2: "🥈", 3: "🥉"}
    lines = ["🎉 *OYUN BAŞA ÇATDI!* 🎉\n"]

    for place, user, cards_left in finish_order:
        emoji = PLACE_EMOJIS.get(place, f"{place}.")
        tag = _rank_tag(user.id)
        name = display_name(user)
        pts = PLACE_POINTS.get(place, 0)
        if cards_left == 0:
            detail = f"✅ Bitirdi (+{pts} xal)"
        else:
            detail = f"{cards_left} kart qaldı (+{pts} xal)"
        lines.append(f"{emoji} *{name}* {tag}\n   _{detail}_")

    context.bot.send_message(
        chat_id=chat_id,
        text="\n".join(lines),
        parse_mode=ParseMode.MARKDOWN,
    )


# ════════════════════════════════════════════════════════════════════════════════
# ACTIVITY MİDDLEWARE — hər mesajda qrup/istifadəçini MongoDB-yə yazır
# ════════════════════════════════════════════════════════════════════════════════

def _activity_register(update: Update, context: CallbackContext):
    """Her gelen mesajda qrup ve istifadecini MongoDB-ye yazar (broadcast ucun)."""
    try:
        if update.effective_chat and update.effective_user:
            if update.effective_chat.type in ("group", "supergroup"):
                add_served_chat(update.effective_chat.id)
            add_served_user(update.effective_user.id)
    except Exception:
        pass


# ════════════════════════════════════════════════════════════════════════════════
# /new  /uno — YENİ OYUN + QEYDIYYAT MENYUSU
# ════════════════════════════════════════════════════════════════════════════════

@user_locale
def new_game(update: Update, context: CallbackContext):
    """Yeni oyun yaradır və qeydiyyat menyusunu göstərir."""
    chat = update.effective_chat
    user = update.effective_user

    if chat.type == "private":
        update.message.reply_text("Bu əmr yalnız qruplarda işləyir. 👥")
        return

    # Broadcast üçün qrubu yaddaşa yaz
    add_served_chat(chat.id)
    add_served_user(user.id)

    # Köhnə oyunları təmizlə, yeni oyun yarat
    game = gm.new_game(chat)
    game.starter = user
    game.owner = [user.id]

    # Yaradıcını avtomatik qoşmaq üçün join et
    try:
        gm.join_game(user, chat)
    except AlreadyJoinedError:
        pass

    msg = update.message.reply_text(
        _lobby_text(game),
        reply_markup=_lobby_keyboard(game),
        parse_mode=ParseMode.MARKDOWN,
    )

    # Mesaj ID-sini saxlayırıq ki, yeniləyə bilək
    context.chat_data["lobby_msg_id"] = msg.message_id

    # Bildiriş göndər
    _send_join_notifications(context, chat.id, user)


def _send_join_notifications(context: CallbackContext, chat_id: int, starter):
    """Yeni oyun başladıqda /notify_me istifadəçilərinə bildiriş göndərir."""
    for uid in remind_dict.get(chat_id, set()):
        if uid != starter.id:
            try:
                context.bot.send_message(
                    uid,
                    f"🔔 {display_name(starter)} yeni UNO oyunu başlatdı!\n"
                    f"Qoşulmaq üçün qrupa gedin.",
                )
            except Exception:
                pass
    remind_dict.pop(chat_id, None)


# ════════════════════════════════════════════════════════════════════════════════
# /join — MÖVCUD LOBBIYƏ QOŞULMA
# ════════════════════════════════════════════════════════════════════════════════

@user_locale
def join_game(update: Update, context: CallbackContext):
    chat = update.effective_chat
    user = update.effective_user

    if chat.type == "private":
        update.message.reply_text("Bu əmr yalnız qruplarda işləyir. 👥")
        return

    add_served_user(user.id)

    try:
        gm.join_game(user, chat)
    except LobbyClosedError:
        update.message.reply_text("🔒 Qeydiyyat bağlıdır.")
        return
    except AlreadyJoinedError:
        update.message.reply_text("Siz artıq oyundasınız! ✅")
        return
    except NoGameInChatError:
        update.message.reply_text("Bu qrupda aktiv oyun yoxdur. /new ilə oyun başladın.")
        return

    game = gm.chatid_games[chat.id][-1]

    if len(game.players) > MAX_PLAYERS:
        gm.leave_game(user, chat)
        update.message.reply_text(f"⛔ Oyunçu sayı maksimuma ({MAX_PLAYERS}) çatıb.")
        return

    update.message.reply_text(f"✅ {display_name(user)} oyuna qoşuldu!")

    lobby_msg_id = context.chat_data.get("lobby_msg_id")
    if lobby_msg_id:
        _update_lobby_message(context, chat.id, lobby_msg_id, game)


# ════════════════════════════════════════════════════════════════════════════════
# CALLBACK QUERY — "Oyuna Qoşul" / "Oyunu Başlat" düymələri
# ════════════════════════════════════════════════════════════════════════════════

def lobby_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    chat = query.message.chat
    user = query.from_user

    add_served_user(user.id)

    games = gm.chatid_games.get(chat.id, [])
    if not games:
        query.answer("Aktiv oyun tapılmadı. /new ilə yenisini başladın.", show_alert=True)
        return

    game = games[-1]

    if query.data == "uno_join":
        if game.started:
            query.answer("Oyun artıq başlayıb! Növbəti oyunu gözləyin.", show_alert=True)
            return
        if len(game.players) >= MAX_PLAYERS:
            query.answer(f"Oyunçu sayı maksimuma ({MAX_PLAYERS}) çatıb.", show_alert=True)
            return
        if not game.open:
            query.answer("🔒 Qeydiyyat bağlıdır.", show_alert=True)
            return

        try:
            gm.join_game(user, chat)
        except AlreadyJoinedError:
            query.answer("Siz artıq oyundasınız! ✅")
            return
        except Exception as e:
            query.answer(str(e), show_alert=True)
            return

        query.answer(f"✅ {user.first_name} qoşuldu!")
        _update_lobby_message(context, chat.id, query.message.message_id, game)

    elif query.data == "uno_start":
        if user.id not in game.owner and not _is_admin(context.bot, user, chat):
            query.answer("Yalnız oyun yaradıcısı başlada bilər!", show_alert=True)
            return
        if len(game.players) < MIN_PLAYERS:
            query.answer(f"Ən az {MIN_PLAYERS} oyunçu lazımdır!", show_alert=True)
            return
        if game.started:
            query.answer("Oyun artıq başlayıb!")
            return

        query.answer("▶️ Oyun başladı!")
        _do_start_game(context, chat, game, query.message.message_id)


def _is_admin(bot, user, chat):
    try:
        member = bot.get_chat_member(chat.id, user.id)
        return member.status in ("administrator", "creator")
    except Exception:
        return False


def _do_start_game(context: CallbackContext, chat, game, lobby_msg_id=None):
    """Oyunu başladır, lobbiyi silir, birinci kartı açır."""
    game.start()

    # Lobbiyi sil
    if lobby_msg_id:
        try:
            context.bot.delete_message(chat.id, lobby_msg_id)
        except Exception:
            pass

    # finish_order saxlama üçün
    game.finish_order = []   # [(place, user, cards_left)]

    context.bot.send_message(
        chat.id,
        f"🃏 *Oyun başladı!* İlk kart: *{repr(game.last_card)}*\n\n"
        f"İndi *{display_name(game.current_player.user)}*-in növbəsidir.\n"
        f"Kart oynamaq üçün ` @botun_adı ` yazın (inline rejim).",
        parse_mode=ParseMode.MARKDOWN,
    )


# ════════════════════════════════════════════════════════════════════════════════
# /start — Oyunu başlat (əmrlə)
# ════════════════════════════════════════════════════════════════════════════════

@user_locale
def start_game(update: Update, context: CallbackContext):
    chat = update.effective_chat
    user = update.effective_user

    if chat.type == "private":
        # Şəxsi söhbətdə /start — xoş gəlmisiniz mesajı
        update.message.reply_text(
            "👋 Salam! Mən UNO botuyam.\n\n"
            "Məni qrupa əlavə edin və /new ilə oyun başladın! 🃏",
        )
        return

    games = gm.chatid_games.get(chat.id, [])
    if not games:
        update.message.reply_text("Aktiv oyun yoxdur. /new ilə yeni oyun başladın.")
        return

    game = games[-1]

    if game.started:
        update.message.reply_text("Oyun artıq başlayıb! 🃏")
        return

    if len(game.players) < MIN_PLAYERS:
        update.message.reply_text(f"Ən az {MIN_PLAYERS} oyunçu lazımdır! ({len(game.players)}/{MIN_PLAYERS})")
        return

    if user.id not in game.owner and not _is_admin(context.bot, user, chat):
        update.message.reply_text("Yalnız oyun yaradıcısı başlada bilər!")
        return

    lobby_msg_id = context.chat_data.get("lobby_msg_id")
    _do_start_game(context, chat, game, lobby_msg_id)


# ════════════════════════════════════════════════════════════════════════════════
# /leave — Oyundan çıxma
# ════════════════════════════════════════════════════════════════════════════════

@user_locale
def leave_game(update: Update, context: CallbackContext):
    chat = update.effective_chat
    user = update.effective_user

    try:
        gm.leave_game(user, chat)
        update.message.reply_text(f"🚪 {display_name(user)} oyundan çıxdı.")
    except NoGameInChatError:
        update.message.reply_text("Bu qrupda aktiv oyun yoxdur.")
    except NotEnoughPlayersError:
        update.message.reply_text("Oyunçu sayı azaldığı üçün oyun dayandırıldı.")
        gm.end_game(chat, user)


# ════════════════════════════════════════════════════════════════════════════════
# /kick — Oyunçunu çıxar
# ════════════════════════════════════════════════════════════════════════════════

@user_locale
def kick_player(update: Update, context: CallbackContext):
    chat = update.effective_chat
    user = update.effective_user

    games = gm.chatid_games.get(chat.id, [])
    if not games:
        update.message.reply_text("Aktiv oyun yoxdur.")
        return

    game = games[-1]

    if not user_is_creator_or_admin(user, game, context.bot, chat):
        update.message.reply_text("Bu əmr yalnız oyun yaradıcısı üçündür.")
        return

    if not update.message.reply_to_message:
        update.message.reply_text("Çıxarmaq istədiyiniz oyunçunun mesajına REPLY edin.")
        return

    kicked = update.message.reply_to_message.from_user
    try:
        gm.leave_game(kicked, chat)
        update.message.reply_text(f"👢 {display_name(kicked)} oyundan çıxarıldı.")
    except Exception as e:
        update.message.reply_text(f"Xəta: {e}")


# ════════════════════════════════════════════════════════════════════════════════
# /close  /open — Lobbini bağla/aç
# ════════════════════════════════════════════════════════════════════════════════

@user_locale
def close_game(update: Update, context: CallbackContext):
    chat = update.effective_chat
    user = update.effective_user
    games = gm.chatid_games.get(chat.id, [])
    if not games:
        update.message.reply_text("Aktiv oyun yoxdur.")
        return
    game = games[-1]
    if not user_is_creator_or_admin(user, game, context.bot, chat):
        update.message.reply_text("Bu əmr yalnız yaradıcı üçündür.")
        return
    game.open = False
    update.message.reply_text("🔒 Qeydiyyat bağlandı.")
    lobby_msg_id = context.chat_data.get("lobby_msg_id")
    if lobby_msg_id:
        _update_lobby_message(context, chat.id, lobby_msg_id, game)


@user_locale
def open_game(update: Update, context: CallbackContext):
    chat = update.effective_chat
    user = update.effective_user
    games = gm.chatid_games.get(chat.id, [])
    if not games:
        update.message.reply_text("Aktiv oyun yoxdur.")
        return
    game = games[-1]
    if not user_is_creator_or_admin(user, game, context.bot, chat):
        update.message.reply_text("Bu əmr yalnız yaradıcı üçündür.")
        return
    game.open = True
    update.message.reply_text("✅ Qeydiyyat açıldı.")
    lobby_msg_id = context.chat_data.get("lobby_msg_id")
    if lobby_msg_id:
        _update_lobby_message(context, chat.id, lobby_msg_id, game)


# ════════════════════════════════════════════════════════════════════════════════
# /stop — Oyunu dayandır
# ════════════════════════════════════════════════════════════════════════════════

@user_locale
def stop_game(update: Update, context: CallbackContext):
    chat = update.effective_chat
    user = update.effective_user
    games = gm.chatid_games.get(chat.id, [])
    if not games:
        update.message.reply_text("Aktiv oyun yoxdur.")
        return
    game = games[-1]
    if not user_is_creator_or_admin(user, game, context.bot, chat):
        update.message.reply_text("Bu əmr yalnız yaradıcı/admin üçündür.")
        return
    gm.end_game(chat, user)
    update.message.reply_text("🛑 Oyun dayandırıldı.")


# ════════════════════════════════════════════════════════════════════════════════
# /skip — Növbəni keç (vaxt aşımı)
# ════════════════════════════════════════════════════════════════════════════════

@user_locale
def skip_player(update: Update, context: CallbackContext):
    chat = update.effective_chat
    user = update.effective_user
    games = gm.chatid_games.get(chat.id, [])
    if not games:
        update.message.reply_text("Aktiv oyun yoxdur.")
        return
    game = games[-1]
    if not game.started:
        update.message.reply_text("Oyun hələ başlamayıb.")
        return

    current = game.current_player
    elapsed = (datetime.now() - current.turn_started).seconds

    if elapsed < current.waiting_time and not user_is_creator_or_admin(user, game, context.bot, chat):
        update.message.reply_text(
            f"⏱ {display_name(current.user)} hələ {current.waiting_time - elapsed} saniyəsi var."
        )
        return

    skipped_name = display_name(current.user)
    game.turn()
    update.message.reply_text(
        f"⏭ {skipped_name} keçildi.\n"
        f"İndi {display_name(game.current_player.user)}-in növbəsidir.",
    )


# ════════════════════════════════════════════════════════════════════════════════
# /notify_me — Yeni oyun bildirişi
# ════════════════════════════════════════════════════════════════════════════════

@user_locale
def notify_me(update: Update, context: CallbackContext):
    chat = update.effective_chat
    user = update.effective_user
    if chat.type == "private":
        update.message.reply_text("Bu əmri qrupda istifadə edin.")
        return
    remind_dict.setdefault(chat.id, set()).add(user.id)
    update.message.reply_text("🔔 Yeni oyun başladıqda sizə bildiriş göndəriləcək!")


# ════════════════════════════════════════════════════════════════════════════════
# INLINE KART OYNAMA
# ════════════════════════════════════════════════════════════════════════════════

@game_locales
@db_session
def reply_to_query(update: Update, context: CallbackContext):
    """Inline sorğunu emal edir — oyunçuya oynaya biləcəyi kartları göstərir."""
    results = list()
    user = update.inline_query.from_user
    query = update.inline_query.query

    add_served_user(user.id)

    try:
        player = gm.userid_current.get(user.id)
        if not player:
            add_no_game(results)
            answer_inline(context.bot, update.inline_query.id, results)
            return

        game = player.game

        # Oyun rejimi seçimi
        if query.startswith("mode_"):
            mode = query.split("_", 1)[1]
            if mode in ("classic", "fast", "wild", "text"):
                game.set_mode(mode)
            add_mode_classic(results)
            add_mode_fast(results)
            add_mode_wild(results)
            add_mode_text(results)
            answer_inline(context.bot, update.inline_query.id, results)
            return

        if not game.started:
            add_not_started(results)
            answer_inline(context.bot, update.inline_query.id, results)
            return

        if player != game.current_player:
            add_gameinfo(game, results)
            add_other_cards(player, results, game)
            answer_inline(context.bot, update.inline_query.id, results)
            return

        if game.choosing_color:
            add_choose_color(results, game)
            add_other_cards(player, results, game)
            answer_inline(context.bot, update.inline_query.id, results)
            return

        playable = player.playable_cards()

        if not player.drew:
            add_draw(player, results)

        if player.drew or game.draw_counter:
            add_pass(results, game)

        if len(player.cards) == 1:
            results.insert(0, InlineQueryResultArticle(
                "uno",
                title="🎴 UNO!",
                description="Son kartınız!",
                input_message_content=InputTextMessageContent("🎴 UNO!")
            ))

        # Bluff çağırma (draw_four sonrası)
        if (game.last_card.special == c.DRAW_FOUR and
                game.current_player == player and
                not player.drew):
            add_call_bluff(results, game)

        for card in sorted(player.cards):
            add_card(game, card, results, card in playable)

        add_other_cards(player, results, game)

    except Exception as e:
        logger.error(f"reply_to_query xətası: {e}", exc_info=True)
        add_no_game(results)

    answer_inline(context.bot, update.inline_query.id, results)


def answer_inline(bot, query_id, results):
    try:
        bot.answer_inline_query(
            query_id, results,
            cache_time=0,
            is_personal=True,
        )
    except Exception as e:
        logger.warning(f"answer_inline xətası: {e}")


# ════════════════════════════════════════════════════════════════════════════════
# CHOSEN INLINE RESULT — Kart seçildi
# ════════════════════════════════════════════════════════════════════════════════

@game_locales
@db_session
def process_result(update: Update, context: CallbackContext):
    """Seçilən kartı emal edir."""
    try:
        user = update.chosen_inline_result.from_user
        result_id = update.chosen_inline_result.result_id
        player = gm.userid_current.get(user.id)

        if not player:
            return

        game = player.game
        chat_id = game.chat.id

        # ─── Rəng seçimi ─────────────────────────────────────────────────────
        if result_id in c.COLORS:
            if game.choosing_color:
                game.choose_color(result_id)
                context.bot.send_message(
                    chat_id,
                    f"🎨 {display_name(user)} rəng seçdi: {display_color(result_id)}\n"
                    f"İndi *{display_name(game.current_player.user)}*-in növbəsidir.",
                    parse_mode=ParseMode.MARKDOWN,
                )
            return

        # ─── Kart çək ────────────────────────────────────────────────────────
        if result_id == "draw":
            if player == game.current_player:
                try:
                    player.draw()
                except Exception:
                    context.bot.send_message(chat_id, "🃏 Dəstdə kart qalmadı.")
                    return
                n = game.draw_counter or 1
                context.bot.send_message(
                    chat_id,
                    f"🃏 {display_name(user)} *{n}* kart götürdü.",
                    parse_mode=ParseMode.MARKDOWN,
                )
            return

        # ─── Pass ─────────────────────────────────────────────────────────────
        if result_id == "pass":
            if player == game.current_player and player.drew:
                game.turn()
                context.bot.send_message(
                    chat_id,
                    f"⏭ {display_name(user)} passsed.\n"
                    f"İndi *{display_name(game.current_player.user)}*-in növbəsidir.",
                    parse_mode=ParseMode.MARKDOWN,
                )
            return

        # ─── Bluff çağır ─────────────────────────────────────────────────────
        if result_id == "call_bluff":
            if player == game.current_player:
                _handle_bluff(context, game, player, chat_id)
            return

        # ─── Oyun rejimi dəyişikliyi ─────────────────────────────────────────
        if result_id.startswith("mode_"):
            mode = result_id[5:]
            if user.id in game.owner or _is_admin(context.bot, user, game.chat):
                game.set_mode(mode)
                context.bot.send_message(chat_id, f"🎮 Oyun rejimi: *{mode}*", parse_mode=ParseMode.MARKDOWN)
            return

        # ─── UNO elan ────────────────────────────────────────────────────────
        if result_id == "uno":
            return

        # ─── Kart oyna ────────────────────────────────────────────────────────
        if player != game.current_player:
            return

        # Kartı tap
        target_card = None
        for card in player.cards:
            if str(card) == result_id:
                target_card = card
                break

        if not target_card or target_card not in player.playable_cards():
            return

        player.play(target_card)

        with db_session:
            us = UserSetting.get(id=user.id)
            if us and us.stats:
                us.cards_played += 1

        # Kart mesajı
        context.bot.send_message(
            chat_id,
            f"🃏 *{display_name(user)}*: {repr(target_card)}",
            parse_mode=ParseMode.MARKDOWN,
        )

        # Oyun bitdi mi?
        if len(player.cards) == 0:
            _on_player_finish(context, game, player, chat_id)
            return

        # Rəng seçim lazımdırsa
        if game.choosing_color:
            context.bot.send_message(
                chat_id,
                f"🎨 *{display_name(user)}* rəng seçməlidir! Inline menyudan seçin.",
                parse_mode=ParseMode.MARKDOWN,
            )
            return

        # Növbəti oyunçu
        context.bot.send_message(
            chat_id,
            f"🎯 İndi *{display_name(game.current_player.user)}*-in növbəsidir.",
            parse_mode=ParseMode.MARKDOWN,
        )

    except Exception as e:
        logger.error(f"process_result xətası: {e}", exc_info=True)


def _handle_bluff(context, game, player, chat_id):
    """Bluff yoxlanılır."""
    bluffer = game.current_player.prev
    if bluffer.bluffing:
        context.bot.send_message(
            chat_id,
            f"😱 {display_name(bluffer.user)} *blöf etdi!* {display_name(player.user)} 4 əvəzinə 2 kart götürür.",
            parse_mode=ParseMode.MARKDOWN,
        )
        game.draw_counter = 2
    else:
        context.bot.send_message(
            chat_id,
            f"😎 {display_name(bluffer.user)} blöf *etmədi!* {display_name(player.user)} 6 kart götürür.",
            parse_mode=ParseMode.MARKDOWN,
        )
        game.draw_counter = 6
    try:
        player.draw()
    except Exception:
        pass
    game.turn()


def _on_player_finish(context: CallbackContext, game, player, chat_id: int):
    """
    Bir oyunçu bütün kartlarını bitirdikdə çağırılır.
    Oyunçu finish_order-ə əlavə edilir.
    Əgər yalnız 1 oyunçu qaldısa — o da sonuncu yer alır, oyun tamamilə bitir.
    """
    if not hasattr(game, "finish_order"):
        game.finish_order = []

    place = len(game.finish_order) + 1
    game.finish_order.append((place, player.user, 0))

    remaining_players = [p for p in game.players if p != player]

    if len(remaining_players) <= 1:
        # Sonuncu oyunçu da bitdi (və ya yalnız biri qaldı)
        if len(remaining_players) == 1:
            last_player = remaining_players[0]
            last_place = len(game.finish_order) + 1
            cards_left = len(last_player.cards)
            game.finish_order.append((last_place, last_player.user, cards_left))

        # Bütün nəticələri MongoDB-yə yaz
        for finish_place, finish_user, _ in game.finish_order:
            record_game_result(finish_user.id, finish_user.first_name, finish_place)
            with db_session:
                us = UserSetting.get(id=finish_user.id)
                if us and us.stats:
                    us.games_played += 1
                    if finish_place == 1:
                        us.first_places += 1

        # Qalibiyyət mesajı
        _announce_results(context, chat_id, game.finish_order)

        # Oyunu bitir
        gm.end_game(game.chat, player.user)

    else:
        # Oyun davam edir, bu oyunçu çıxır
        context.bot.send_message(
            chat_id,
            f"🎉 *{display_name(player.user)}* {place}-ci yeri tutdu! (UNO!)\n"
            f"Oyun davam edir — {len(remaining_players)} oyunçu qalıb.",
            parse_mode=ParseMode.MARKDOWN,
        )
        player.leave()
        game.turn()

        context.bot.send_message(
            chat_id,
            f"🎯 İndi *{display_name(game.current_player.user)}*-in növbəsidir.",
            parse_mode=ParseMode.MARKDOWN,
        )


# ════════════════════════════════════════════════════════════════════════════════
# /profile — Oyunçu profili
# ════════════════════════════════════════════════════════════════════════════════

def profile_command(update: Update, context: CallbackContext):
    user = update.effective_user
    add_served_user(user.id)

    prof = get_profile(user.id)
    if not prof:
        update.message.reply_text(
            "👤 Hələ profiliniz yoxdur.\nBir oyun oynayın! 🃏",
        )
        return

    points = prof.get("total_points", 0)
    level, rank_name, rank_emoji = get_rank(points)

    text = (
        f"👤 *Oyunçu: {display_name(user)}*\n\n"
        f"🏅 *Rütbə:* {rank_emoji} {rank_name}\n"
        f"⭐ *Səviyyə:* {level}\n\n"
        f"🎮 *Oyun:* {prof.get('games_played', 0)}\n"
        f"🏆 *Qələbə:* {prof.get('wins', 0)}\n"
        f"💎 *Ümumi Xal:* {points}"
    )
    update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


# ════════════════════════════════════════════════════════════════════════════════
# /rating — Top 25
# ════════════════════════════════════════════════════════════════════════════════

def rating_command(update: Update, context: CallbackContext):
    top = get_top_ratings(25)
    if not top:
        update.message.reply_text("Reytinq siyahısı hələ boşdur. Oyun oynayın! 🃏")
        return

    PLACE_EMOJIS = {1: "🥇", 2: "🥈", 3: "🥉"}
    lines = ["👑 *UNO Reytinq Siyahısı (Top 25):*\n"]

    for i, doc in enumerate(top, 1):
        pts = doc.get("total_points", 0)
        level, rank_name, rank_emoji = get_rank(pts)
        name = doc.get("name", "Anonim")
        wins = doc.get("wins", 0)
        emoji = PLACE_EMOJIS.get(i, f"{i}.")
        lines.append(
            f"{emoji} *{name}* {rank_emoji}{level} _{rank_name}_\n"
            f"   🏆 {wins} qələbə | 💎 {pts} xal"
        )

    update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


# ════════════════════════════════════════════════════════════════════════════════
# /broadcast — Bütün qrup+istifadəçilərə mesaj göndər
# ════════════════════════════════════════════════════════════════════════════════

def broadcast_command(update: Update, context: CallbackContext):
    user = update.effective_user

    if str(user.id) not in SUDO_USERS:
        update.message.reply_text("⛔ Bu əmr yalnız adminlər üçündür.")
        return

    if not update.message.reply_to_message:
        update.message.reply_text(
            "✍️ Yaymaq istədiyiniz mesaja REPLY edərək /broadcast yazın.\n"
            "(Şəkil, mətn, kanal postu — hər şey olar)"
        )
        return

    source_chat = update.message.chat.id
    source_msg = update.message.reply_to_message.message_id

    status = update.message.reply_text("⚡ Broadcast başladı, gözləyin...")

    sent_c, fail_c = 0, 0
    for chat in get_served_chats():
        cid = chat["chat_id"]
        try:
            context.bot.forward_message(cid, source_chat, source_msg)
            sent_c += 1
            time.sleep(0.05)
        except Exception as e:
            log_broadcast_error("chat", cid, str(e))
            fail_c += 1

    sent_u, fail_u = 0, 0
    for u in get_served_users():
        uid = u["user_id"]
        try:
            context.bot.forward_message(uid, source_chat, source_msg)
            sent_u += 1
            time.sleep(0.05)
        except Exception as e:
            log_broadcast_error("user", uid, str(e))
            fail_u += 1

    try:
        status.edit_text(
            f"✅ Broadcast tamamlandı!\n\n"
            f"👥 Qruplar: {sent_c} uğurlu, {fail_c} uğursuz\n"
            f"👤 İstifadəçilər: {sent_u} uğurlu, {fail_u} uğursuz"
        )
    except Exception:
        pass


# ════════════════════════════════════════════════════════════════════════════════
# Bot qrupa əlavə edildi — avtomatik yaddaşa yaz
# ════════════════════════════════════════════════════════════════════════════════

def new_member_handler(update: Update, context: CallbackContext):
    """Bot qrupa əlavə olunanda avtomatik yaddaşa yazılır."""
    bot_id = context.bot.id
    for member in update.message.new_chat_members:
        if member.id == bot_id:
            add_served_chat(update.effective_chat.id)
            context.bot.send_message(
                update.effective_chat.id,
                "✨ Məni bu qrupa əlavə etdiyiniz üçün təşəkkür edirəm! 😊\n\n"
                "🃏 UNO oyununu başlatmaq üçün */new* yazın.",
                parse_mode=ParseMode.MARKDOWN,
            )
            break


# ════════════════════════════════════════════════════════════════════════════════
# HANDLER QEYDİYYATI
# ════════════════════════════════════════════════════════════════════════════════

def register_handlers():
    # Activity middleware (hər mesajda çağırılır)
    dispatcher.add_handler(
        MessageHandler(Filters.all & ~Filters.command, _activity_register),
        group=-1
    )
    dispatcher.add_handler(
        MessageHandler(Filters.command, _activity_register),
        group=-1
    )

    # Bot qrupa əlavə edildi
    dispatcher.add_handler(
        MessageHandler(Filters.status_update.new_chat_members, new_member_handler)
    )

    # Oyun əmrləri
    dispatcher.add_handler(CommandHandler(["new", "uno"], new_game))
    dispatcher.add_handler(CommandHandler("join", join_game))
    dispatcher.add_handler(CommandHandler("start", start_game))
    dispatcher.add_handler(CommandHandler("leave", leave_game))
    dispatcher.add_handler(CommandHandler("kick", kick_player))
    dispatcher.add_handler(CommandHandler("close", close_game))
    dispatcher.add_handler(CommandHandler("open", open_game))
    dispatcher.add_handler(CommandHandler("stop", stop_game))
    dispatcher.add_handler(CommandHandler("skip", skip_player))
    dispatcher.add_handler(CommandHandler("notify_me", notify_me))

    # Profil və reytinq
    dispatcher.add_handler(CommandHandler("profile", profile_command))
    dispatcher.add_handler(CommandHandler("rating", rating_command))

    # Broadcast (admin)
    dispatcher.add_handler(CommandHandler("broadcast", broadcast_command))

    # Lobby callback düymələri
    dispatcher.add_handler(
        CallbackQueryHandler(lobby_callback, pattern="^uno_(join|start)$")
    )

    # Inline kart oynama
    dispatcher.add_handler(InlineQueryHandler(reply_to_query))
    dispatcher.add_handler(ChosenInlineResultHandler(process_result))

    # Köhnə əmrləri saxla (simple_commands.py və settings.py)
    from simple_commands import register as sc_register
    from settings import register as st_register
    sc_register()
    st_register()

    logger.info("✅ Bütün handler-lər qeydiyyatdan keçdi.")


# ════════════════════════════════════════════════════════════════════════════════
# ANA PROQRAM
# ════════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    register_handlers()
    logger.info("🚀 UNO Bot başladı...")
    from start_bot import start_bot
    start_bot(updater)
