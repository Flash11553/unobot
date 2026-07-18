#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Domino botundakı "Oyuna Qeydiyyat" menyusunun UNO botu üçün versiyası:
#   - "Oyuna Qoşul 🙋‍♂️" düyməsi, 2+ oyunçu olanda "Oyunu Başlat ▶️" düyməsi
#   - Qoşulanların siyahısı (adı + səviyyəsi/rütbəsi) mesajda göstərilir
#   - Maksimum 10 oyunçu
#   - 5 dəqiqə ərzində oyun başlamasa lobby avtomatik bağlanır

import logging
from datetime import datetime, timedelta

from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import CallbackContext

from config import MIN_PLAYERS, MAX_PLAYERS, LOBBY_TIMEOUT_MINUTES
from errors import NoGameInChatError
from shared_vars import gm
from user_setting import UserSetting
from levels import compute_level
from utils import display_name

logger = logging.getLogger(__name__)


def get_player_level_label(user) -> str:
    """Oyunçunun adı + səviyyəsi/rütbəsini qaytarır (yalnız lobby və
    final nəticə mesajlarında istifadə olunur, oyun gedişatında YOX)."""
    us = UserSetting.get(id=user.id)
    wins = us.first_places if us else 0
    level, rank_name = compute_level(wins)
    return f"{display_name(user)} — {rank_name} ⭐{level}"


def get_lobby_keyboard(players_count: int) -> InlineKeyboardMarkup:
    kb = [[InlineKeyboardButton("Oyuna Qoşul 🙋‍♂️", callback_data="uno_lobby_join")]]
    if players_count >= MIN_PLAYERS:
        kb[0].append(
            InlineKeyboardButton("Oyunu Başlat ▶️", callback_data="uno_lobby_start")
        )
    return InlineKeyboardMarkup(kb)


def build_lobby_text(game) -> str:
    players = game.players
    names = "\n".join(f"• {get_player_level_label(p.user)}" for p in players) or \
        "Hələ kimsə qoşulmayıb."

    return (
        "🎮 <b>UNO Oyununa Qeydiyyat Başladı!</b>\n\n"
        f"<b>Qoşulanlar ({len(players)}/{MAX_PLAYERS} nəfər):</b>\n"
        f"{names}\n\n"
        f"(Başlamaq üçün ən az {MIN_PLAYERS} nəfər lazımdır)"
    )


def update_lobby_message(bot, chat_id, game):
    if not game or game.lobby_message_id is None:
        return
    try:
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=game.lobby_message_id,
            text=build_lobby_text(game),
            reply_markup=get_lobby_keyboard(len(game.players)),
            parse_mode="HTML",
        )
    except Exception as e:
        logger.warning(f"Lobby mesajı yenilənmədi: {e}")


def send_lobby_message(bot, chat_id, game):
    sent = bot.send_message(
        chat_id=chat_id,
        text=build_lobby_text(game),
        reply_markup=get_lobby_keyboard(len(game.players)),
        parse_mode="HTML",
    )
    game.lobby_message_id = sent.message_id
    game.last_lobby_activity = datetime.now()
    return sent


def close_lobby_tracking(game):
    """Oyun başlayanda (və ya bağlananda) lobby-timeout izləməsini dayandırır."""
    game.last_lobby_activity = None


def get_open_lobby(chat_id):
    """Bu qrupda hələ başlamamış (lobby mərhələsində olan) oyun varsa qaytarır."""
    games = gm.chatid_games.get(chat_id)
    if not games:
        return None
    game = games[-1]
    if not game.started:
        return game
    return None


def get_active_game(chat_id):
    """Bu qrupda HƏR HANSI aktiv oyun (lobby VƏ YA artıq başlamış) varsa qaytarır."""
    games = gm.chatid_games.get(chat_id)
    if not games:
        return None
    return games[-1]


def force_end_game(chat, game):
    """Oyunu MƏCBURİ bitirir - gm.end_game-in 'user mütləq oyunçu olmalıdır'
    asılılığından yan keçir (məs. admin lobby-yə özü qoşulmayıbsa, və ya
    hərəkətsizlik/timeout səbəbindən avtomatik bağlananda)."""
    if game.players:
        try:
            gm.end_game(chat, game.players[0].user)
            return
        except NoGameInChatError:
            pass

    games_list = gm.chatid_games.get(chat.id)
    if games_list and game in games_list:
        games_list.remove(game)
        if not games_list:
            del gm.chatid_games[chat.id]


def check_inactive_lobbies_job(context: CallbackContext):
    """Job queue tərəfindən mütəmadi çağırılır (bax: bot.py).
    - 5 dəqiqə ərzində başlamayan lobby-ləri avtomatik bağlayır
    - HƏMÇİNİN 5 dəqiqə ərzində heç bir hərəkət (kart oynama, sıra keçmə)
      olmayan artıq BAŞLAMIŞ oyunları da avtomatik sonlandırır"""
    bot = context.bot
    now = datetime.now()
    threshold = now - timedelta(minutes=LOBBY_TIMEOUT_MINUTES)

    for chat_id, games in list(gm.chatid_games.items()):
        for game in list(games):

            if not game.started:
                # ---- Qeydiyyat (lobby) mərhələsi hərəkətsizdirsə ----
                last_activity = game.last_lobby_activity
                if not last_activity or last_activity >= threshold:
                    continue

                players_count = len(game.players)

                try:
                    if game.lobby_message_id is not None:
                        try:
                            bot.delete_message(chat_id, game.lobby_message_id)
                        except Exception:
                            pass

                    games.remove(game)
                    if not games:
                        del gm.chatid_games[chat_id]

                    if players_count < MIN_PLAYERS:
                        text = (
                            f"⏳ **Oyun Dayandırıldı**\n"
                            f"Qeydiyyat başlayandan **{LOBBY_TIMEOUT_MINUTES} dəqiqə** keçdi, "
                            f"lakin ən az {MIN_PLAYERS} oyunçu qoşulmadı. "
                            f"Yeni oyun üçün /uno yazın ✅"
                        )
                    else:
                        text = (
                            f"⏳ **Oyun Dayandırıldı**\n"
                            f"Qeydiyyat başlayandan **{LOBBY_TIMEOUT_MINUTES} dəqiqə** keçdi. "
                            f"Kifayət qədər oyunçu olsa da, oyun başladılmadı. "
                            f"Yeni oyun üçün /uno yazın ✅"
                        )

                    bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown")
                    logger.info(f"Lobby timeout ilə bağlandı. Chat ID: {chat_id}")
                except Exception as e:
                    logger.error(f"Lobby timeout bildirişi göndərilərkən xəta: {e}")

            else:
                # ---- Artıq başlamış, amma hərəkətsiz qalmış oyun ----
                last_activity = getattr(game, "last_activity", None)
                if not last_activity or last_activity >= threshold:
                    continue

                try:
                    force_end_game(game.chat, game)
                    bot.send_message(
                        chat_id=chat_id,
                        text=(
                            f"⏳ **Oyun Dayandırıldı**\n"
                            f"Oyunda **{LOBBY_TIMEOUT_MINUTES} dəqiqədir** heç bir hərəkət "
                            f"olmadığı üçün avtomatik sonlandırıldı. "
                            f"Yeni oyun üçün /uno yazın ✅"
                        ),
                        parse_mode="Markdown",
                    )
                    logger.info(f"Hərəkətsizlik səbəbindən oyun sonlandırıldı. Chat ID: {chat_id}")
                except Exception as e:
                    logger.error(f"Hərəkətsiz oyun sonlandırılarkən xəta: {e}")
