#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Telegram bot to play UNO in group chats
# Copyright (c) 2016 Jannes Höke <uno@jhoeke.de>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

import logging
from datetime import datetime

from telegram import ParseMode, InlineKeyboardMarkup, \
    InlineKeyboardButton, Update
from telegram.ext import InlineQueryHandler, ChosenInlineResultHandler, \
    CommandHandler, MessageHandler, Filters, CallbackQueryHandler, CallbackContext
from telegram.ext.dispatcher import run_async

import card as c
import settings
import simple_commands
import broadcast
from broadcast_store import add_served_chat, add_served_user
from actions import (do_skip, do_play_card, do_draw, do_call_bluff,
                     process_departure)
from config import DEFAULT_GAMEMODE, MIN_PLAYERS, MAX_PLAYERS, LOBBY_TIMEOUT_MINUTES
from errors import (NoGameInChatError, LobbyClosedError, AlreadyJoinedError,
                    NotEnoughPlayersError, DeckEmptyError)
from internationalization import _, __, user_locale, game_locales
from lobby import (get_lobby_keyboard, build_lobby_text, update_lobby_message,
                   send_lobby_message, close_lobby_tracking, get_open_lobby,
                   get_active_game, force_end_game, check_inactive_lobbies_job)
from results import (add_call_bluff, add_choose_color, add_draw, add_gameinfo,
                     add_no_game, add_not_started, add_other_cards, add_pass,
                     add_card, add_mode_classic, add_mode_fast, add_mode_wild, add_mode_text)
from shared_vars import gm, updater, dispatcher
from simple_commands import help_handler
from start_bot import start_bot
from utils import display_name
from utils import send_async, answer_async, error, TIMEOUT, user_is_creator_or_admin, user_is_creator, game_is_running


logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)
logging.getLogger('apscheduler').setLevel(logging.WARNING)


def _group_only_notice(update: Update, context: CallbackContext):
    """Yalnız qrupda işləyən əmrlər şəxsi mesajda yazılanda göstərilir."""
    send_async(context.bot, update.message.chat_id,
               text=_("⚠️ Bu əmr yalnız qrup daxilində işləyir."))

@user_locale
def notify_me(update: Update, context: CallbackContext):
    """Handler for /notify_me command, pm people for next game"""
    chat_id = update.message.chat_id
    if update.message.chat.type == 'private':
        _group_only_notice(update, context)
    else:
        try:
            gm.remind_dict[chat_id].add(update.message.from_user.id)
        except KeyError:
            gm.remind_dict[chat_id] = {update.message.from_user.id}


@user_locale
def new_game(update: Update, context: CallbackContext):
    """Handler for the /new (and /uno) command"""
    chat_id = update.message.chat_id

    add_served_chat(chat_id)
    add_served_user(update.message.from_user.id)

    if update.message.chat.type == 'private':
        _group_only_notice(update, context)
        return

    # 🟢 Artıq aktiv oyun (qeydiyyat VƏ YA gedişat mərhələsində) varsa,
    # yeni qeydiyyat menyusu açmaq əvəzinə xəbərdarlıq göndər
    active_game = get_active_game(chat_id)
    if active_game is not None:
        if not active_game.started:
            send_async(context.bot, chat_id,
                       text=_("✅ Artıq aktiv qeydiyyat menyusu var. "
                              "Oyunu sonlandırmaq üçün: /stop"))
        else:
            send_async(context.bot, chat_id,
                       text=_("⚠️ Artıq qrupda aktiv UNO oyunu gedir, hələ bitməyib. "
                              "Oyunu sonlandırmaq üçün: /stop"))
        return

    if update.message.chat_id in gm.remind_dict:
        for user in gm.remind_dict[update.message.chat_id]:
            send_async(context.bot,
                       user,
                       text=_("Yeni oyun başlayır {title}").format(
                            title=update.message.chat.title))

        del gm.remind_dict[update.message.chat_id]

    game = gm.new_game(update.message.chat)
    game.starter = update.message.from_user
    game.owner = set()
    game.owner.add(update.message.from_user.id)
    game.mode = DEFAULT_GAMEMODE

    # 🟢 Domino botundakı kimi interaktiv qeydiyyat menyusu
    send_lobby_message(context.bot, chat_id, game)


@user_locale
def kill_game(update: Update, context: CallbackContext):
    """Handler for the /kill command"""
    chat = update.message.chat
    user = update.message.from_user
    games = gm.chatid_games.get(chat.id)

    if update.message.chat.type == 'private':
        _group_only_notice(update, context)
        return

    if not games:
            send_async(context.bot, chat.id,
                       text=_("Bu Qrupda heç bir oyun oynanılmır."))
            return

    game = games[-1]

    if user_is_creator_or_admin(user, game, context.bot, chat):

        if game.lobby_message_id is not None:
            try:
                context.bot.delete_message(chat.id, game.lobby_message_id)
            except Exception:
                pass

        force_end_game(chat, game)

        send_async(context.bot, chat.id,
                   text=_("❌ Aktiv uno oyunu sonlandırıldı. "
                          "Yeni oyunu başlatmaq üçün /uno yazın."))

    else:
        send_async(context.bot, chat.id,
                  text=_("Ancaq Oyunu başladan ({name}) bu əmri icra edə bilər")
                  .format(name=game.starter.first_name),
                  reply_to_message_id=update.message.message_id)

@user_locale
def join_game(update: Update, context: CallbackContext):
    """Handler for the /join command"""
    chat = update.message.chat

    if update.message.chat.type == 'private':
        _group_only_notice(update, context)
        return

    lobby_game = get_open_lobby(chat.id)
    if lobby_game is not None and len(lobby_game.players) >= MAX_PLAYERS:
        send_async(context.bot, chat.id,
                   text=_("⚠️ Oyunçu sayı artıq maksimuma ({max} nəfər) çatıb.")
                   .format(max=MAX_PLAYERS),
                   reply_to_message_id=update.message.message_id)
        return

    try:
        gm.join_game(update.message.from_user, chat)

    except LobbyClosedError:
            send_async(context.bot, chat.id, text=_("Oyuna qeydiyyat bağlanıb"))

    except NoGameInChatError:
        send_async(context.bot, chat.id,
                   text=_("Heç bir Oyun getmir indi. "
                          "Yeni oyun bu əmr ilə yarat: /new"),
                   reply_to_message_id=update.message.message_id)

    except AlreadyJoinedError:
        send_async(context.bot, chat.id,
                   text=_("Sən artıq oyuna qoşulmusan ✅"),
                   reply_to_message_id=update.message.message_id)

    except DeckEmptyError:
        send_async(context.bot, chat.id,
                   text=_("Əlinizdə kifayət qədər kart qalmayıb"
                          "yeni oyunçuların qoşulması üçün."),
                   reply_to_message_id=update.message.message_id)

    else:
        send_async(context.bot, chat.id,
                   text=_("✅ Oyunçu {name} oyuna qoşuldu!")
                   .format(name=display_name(update.message.from_user)))
        refreshed_lobby = get_open_lobby(chat.id)
        if refreshed_lobby is not None:
            update_lobby_message(context.bot, chat.id, refreshed_lobby)


@user_locale
def leave_game(update: Update, context: CallbackContext):
    """Handler for the /leave command"""
    chat = update.message.chat
    user = update.message.from_user

    if update.message.chat.type == 'private':
        _group_only_notice(update, context)
        return

    player = gm.player_for_user_in_chat(user, chat)

    if player is None:
        send_async(context.bot, chat.id, text=_("Siz oynamırsız bu qrupdaki oyunda"),
                   reply_to_message_id=update.message.message_id)
        return

    game = player.game

    if not game.started:
        # Oyun hələ başlamayıb (lobby mərhələsi) - yer (placement) izləməsi lazım deyil
        try:
            gm.leave_game(user, chat)
        except NoGameInChatError:
            send_async(context.bot, chat.id, text=_("Siz oynamırsız bu qrupdaki oyunda"),
                       reply_to_message_id=update.message.message_id)
            return

        send_async(context.bot, chat.id,
                   text=__("{name} oyunu tərk etdi oyun başlamadan əvvəl .",
                           multi=game.translate).format(
                       name=display_name(user)),
                   reply_to_message_id=update.message.message_id)
        refreshed_lobby = get_open_lobby(chat.id)
        if refreshed_lobby is not None:
            update_lobby_message(context.bot, chat.id, refreshed_lobby)
        return

    # 🟢 Oyun artıq gedir - tərk edən oyunçu sıralamada sonuncu yerlərdən
    # birinə yazılır (domino botundakı kimi)
    try:
        ended = process_departure(context.bot, chat, game, user)
    except NoGameInChatError:
        send_async(context.bot, chat.id, text=_("Siz oynamırsız bu qrupdaki oyunda"),
                   reply_to_message_id=update.message.message_id)
        return

    if not ended:
        send_async(context.bot, chat.id,
                   text=__("Tamam. Növbəti oyunçu: {name}",
                           multi=game.translate).format(
                       name=display_name(game.current_player.user)),
                   reply_to_message_id=update.message.message_id)


@user_locale
def lobby_join_callback(update: Update, context: CallbackContext):
    """Handler for the 'Oyuna Qoşul 🙋‍♂️' lobby button"""
    query = update.callback_query
    chat = query.message.chat
    user = query.from_user

    game = get_open_lobby(chat.id)
    if game is None:
        query.answer(_("Oyun bitib. /new ilə yenisini başladın."), show_alert=True)
        return

    if len(game.players) >= MAX_PLAYERS:
        query.answer(_("Oyunçu sayı artıq maksimuma ({max} nəfər) çatıb.")
                     .format(max=MAX_PLAYERS), show_alert=True)
        return

    try:
        gm.join_game(user, chat)
    except LobbyClosedError:
        query.answer(_("Oyuna qeydiyyat bağlanıb"), show_alert=True)
        return
    except AlreadyJoinedError:
        query.answer(_("Sən artıq oyuna qoşulmusan ✅"), show_alert=True)
        return
    except DeckEmptyError:
        query.answer(_("Əlinizdə kifayət qədər kart qalmayıb yeni oyunçuların qoşulması üçün."),
                     show_alert=True)
        return
    except NoGameInChatError:
        query.answer(_("Oyun tapılmadı."), show_alert=True)
        return

    game.last_lobby_activity = datetime.now()
    update_lobby_message(context.bot, chat.id, game)
    query.answer(_("Oyuna qoşuldunuz!"), show_alert=False)
    send_async(context.bot, chat.id,
               text=_("✅ Oyunçu {name} oyuna qoşuldu!").format(name=display_name(user)))


@user_locale
def lobby_start_callback(update: Update, context: CallbackContext):
    """Handler for the 'Oyunu Başlat ▶️' lobby button"""
    query = update.callback_query
    chat = query.message.chat

    game = get_open_lobby(chat.id)
    if game is None:
        query.answer(_("Oyun tapılmadı."), show_alert=True)
        return

    if len(game.players) < MIN_PLAYERS:
        query.answer(_("Oyunçular çatışmır (min {min} nəfər).")
                     .format(min=MIN_PLAYERS), show_alert=True)
        return

    query.answer(_("Oyun Başladı!"))
    perform_game_start(context.bot, context.job_queue, chat, game)


def select_game(update: Update, context: CallbackContext):
    """Handler for callback queries to select the current game"""

    chat_id = int(update.callback_query.data)
    user_id = update.callback_query.from_user.id
    players = gm.userid_players[user_id]
    for player in players:
        if player.game.chat.id == chat_id:
            gm.userid_current[user_id] = player
            break
    else:
        send_async(bot,
                   update.callback_query.message.chat_id,
                   text=_("Oyun Tapılmadı."))
        return

    def selected():
        back = [[InlineKeyboardButton(text=_("Sonuncu qrupa qayıt"),
                                      switch_inline_query='')]]
        context.bot.answerCallbackQuery(update.callback_query.id,
                                text=_("Zəhmət olmasa siz seçdiyiniz qrupa çevirin!"),
                                show_alert=False,
                                timeout=TIMEOUT)

        context.bot.editMessageText(chat_id=update.callback_query.message.chat_id,
                            message_id=update.callback_query.message.message_id,
                            text=_("Seçilmiş qrup: {group}\n"
                                   "<b>Əmin olun ki düzgün qrupa çevirdiz"
                                   "qrup!</b>").format(
                                group=gm.userid_current[user_id].game.chat.title),
                            reply_markup=InlineKeyboardMarkup(back),
                            parse_mode=ParseMode.HTML,
                            timeout=TIMEOUT)

    dispatcher.run_async(selected)


@game_locales
def status_update(update: Update, context: CallbackContext):
    """Remove player from game if user leaves the group"""
    chat = update.message.chat

    if update.message.left_chat_member:
        user = update.message.left_chat_member
        player = gm.player_for_user_in_chat(user, chat)

        if player is None:
            return

        game = player.game

        if not game.started:
            try:
                gm.leave_game(user, chat)
            except NoGameInChatError:
                pass
            return

        try:
            ended = process_departure(context.bot, chat, game, user)
        except NoGameInChatError:
            return

        if not ended:
            send_async(context.bot, chat.id, text=__("{name} kənarlaşdırılır oyundan",
                                             multi=game.translate)
                       .format(name=display_name(user)))


def perform_game_start(bot, job_queue, chat, game):
    """Oyunu faktiki başladan ortaq funksiya - HƏM /start əmri, HƏM DƏ
    qeydiyyat menyusundakı 'Oyunu Başlat ▶️' düyməsi bunu çağırır ki, hər iki
    üsulla oyun eyni məntiqlə başlasın."""

    # 🟢 Qeydiyyat menyusunu bağla (oyun artıq başlayır)
    if game.lobby_message_id is not None:
        try:
            bot.delete_message(chat.id, game.lobby_message_id)
        except Exception:
            pass
        game.lobby_message_id = None
    close_lobby_tracking(game)

    game.start()

    for player in game.players:
        player.draw_first_hand()
    choice = [[InlineKeyboardButton(text=_("Seçiminizi Edin!"), switch_inline_query_current_chat='')]]
    first_message = (
        __("İlk Oyunçu: {name}\n"
           "/close edərək başqalarının oyuna qoşulmağını bağlayın.\n")
        .format(name=display_name(game.current_player.user)))

    def send_first():
        """Send the first card and player"""

        bot.sendSticker(chat.id,
                        sticker=c.STICKERS[str(game.last_card)],
                        timeout=TIMEOUT)

        bot.sendMessage(chat.id,
                        text=first_message,
                        reply_markup=InlineKeyboardMarkup(choice),
                        timeout=TIMEOUT)

    dispatcher.run_async(send_first)


@user_locale
def start_game(update: Update, context: CallbackContext):
    """Handler for the /start command.
    Əgər qrupda açıq qeydiyyat menyusu varsa, /start elə "Oyunu Başlat ▶️"
    düyməsi kimi işləyir və oyunu başladır. Əks halda (və şəxsi mesajda)
    sadəcə /help mesajını göstərir."""
    chat = update.effective_chat
    user = update.effective_user

    if user:
        add_served_user(user.id)
    if chat is not None and chat.type != 'private':
        add_served_chat(chat.id)

    if chat is not None and chat.type != 'private':
        lobby = get_open_lobby(chat.id)
        if lobby is not None:
            if len(lobby.players) < MIN_PLAYERS:
                send_async(context.bot, chat.id,
                           text=__("Ən azından {minplayers} oyunçu qoşulmalıdır oyuna, "
                                  "sizin oyuna start etməyiniz üçün").format(minplayers=MIN_PLAYERS))
                return
            perform_game_start(context.bot, context.job_queue, chat, lobby)
            return

    help_handler(update, context)


@user_locale
def close_game(update: Update, context: CallbackContext):
    """Handler for the /close command"""
    chat = update.message.chat
    user = update.message.from_user

    if update.message.chat.type == 'private':
        _group_only_notice(update, context)
        return

    games = gm.chatid_games.get(chat.id)

    if not games:
        send_async(context.bot, chat.id,
                   text=_("Bu Qrupda heç bir Oyun oynanılmır."))
        return

    game = games[-1]

    if user.id in game.owner:
        game.open = False
        send_async(context.bot, chat.id, text=_("Oyuna qeydiyyat bağlandı. "
                                        "Bu oyuna artıq heç kim qoşula bilməz."))
        return

    else:
        send_async(context.bot, chat.id,
                   text=_("Ancaq Oyunu başladan ({name}) bunu edə bilər.")
                   .format(name=game.starter.first_name),
                   reply_to_message_id=update.message.message_id)
        return


@user_locale
def open_game(update: Update, context: CallbackContext):
    """Handler for the /open command"""
    chat = update.message.chat
    user = update.message.from_user

    if update.message.chat.type == 'private':
        _group_only_notice(update, context)
        return

    games = gm.chatid_games.get(chat.id)

    if not games:
        send_async(context.bot, chat.id,
                   text=_("Bu Qrupda heç bir Oyun oynanılmır"))
        return

    game = games[-1]

    if user.id in game.owner:
        game.open = True
        send_async(context.bot, chat.id, text=_("Oyuna Qeydiyyat açıldı. Yeni oyunçular /join yazaraq oyuna qoşula bilərlər."))
        return
    else:
        send_async(context.bot, chat.id,
                   text=_("Ancaq Oyunu başladan({name}) bunu edə bilər.")
                   .format(name=game.starter.first_name),
                   reply_to_message_id=update.message.message_id)
        return


@user_locale
def enable_translations(update: Update, context: CallbackContext):
    """Handler for the /enable_translations command"""
    chat = update.message.chat
    user = update.message.from_user
    games = gm.chatid_games.get(chat.id)

    if not games:
        send_async(context.bot, chat.id,
                   text=_("There is no running game in this chat."))
        return

    game = games[-1]

    if user.id in game.owner:
        game.translate = True
        send_async(context.bot, chat.id, text=_("Enabled multi-translations. "
                                        "Disable with /disable_translations"))
        return

    else:
        send_async(context.bot, chat.id,
                   text=_("Only the game creator ({name}) and admin can do that.")
                   .format(name=game.starter.first_name),
                   reply_to_message_id=update.message.message_id)
        return


@user_locale
def disable_translations(update: Update, context: CallbackContext):
    """Handler for the /disable_translations command"""
    chat = update.message.chat
    user = update.message.from_user
    games = gm.chatid_games.get(chat.id)

    if not games:
        send_async(context.bot, chat.id,
                   text=_("There is no running game in this chat."))
        return

    game = games[-1]

    if user.id in game.owner:
        game.translate = False
        send_async(context.bot, chat.id, text=_("Disabled multi-translations. "
                                        "Enable them again with "
                                        "/enable_translations"))
        return

    else:
        send_async(context.bot, chat.id,
                   text=_("Only the game creator ({name}) and admin can do that.")
                   .format(name=game.starter.first_name),
                   reply_to_message_id=update.message.message_id)
        return


@game_locales
@user_locale
def skip_player(update: Update, context: CallbackContext):
    """Handler for the /skip command - sıradakı oyunçunu oyundan çıxarır
    (yalnız 3+ oyunçu qalanda mümkündür) və növbəni keçirir."""
    chat = update.message.chat
    user = update.message.from_user

    if update.message.chat.type == 'private':
        _group_only_notice(update, context)
        return

    player = gm.player_for_user_in_chat(user, chat)
    if not player:
        send_async(context.bot, chat.id,
                   text=_("Siz Oyun oynamırsız bu qrupda ."))
        return

    game = player.game

    if not game.started:
        send_async(context.bot, chat.id,
                   text=_("Oyun hələ başlamayıb."))
        return

    do_skip(context.bot, game)


@game_locales
@user_locale
def reply_to_query(update: Update, context: CallbackContext):
    """
    Handler for inline queries.
    Builds the result list for inline queries and answers to the client.
    """
    results = list()
    switch = None

    try:
        user = update.inline_query.from_user
        user_id = user.id
        players = gm.userid_players[user_id]
        player = gm.userid_current[user_id]
        game = player.game
    except KeyError:
        add_no_game(results)
    else:

        # The game has not started.
        # The creator may change the game mode, other users just get a "game has not started" message.
        if not game.started:
            if user_is_creator(user, game):
                add_mode_classic(results)
                add_mode_fast(results)
                add_mode_wild(results)
                add_mode_text(results)
            else:
                add_not_started(results)


        elif user_id == game.current_player.user.id:
            if game.choosing_color:
                add_choose_color(results, game)
                add_other_cards(player, results, game)
            else:
                if not player.drew:
                    add_draw(player, results)

                else:
                    add_pass(results, game)

                if game.last_card.special == c.DRAW_FOUR and game.draw_counter:
                    add_call_bluff(results, game)

                playable = player.playable_cards()
                added_ids = list()  # Duplicates are not allowed

                for card in sorted(player.cards):
                    add_card(game, card, results,
                             can_play=(card in playable and
                                            str(card) not in added_ids))
                    added_ids.append(str(card))

                add_gameinfo(game, results)

        elif user_id != game.current_player.user.id or not game.started:
            for card in sorted(player.cards):
                add_card(game, card, results, can_play=False)

        else:
            add_gameinfo(game, results)

        for result in results:
            result.id += ':%d' % player.anti_cheat

        if players and game and len(players) > 1:
            switch = _('İndiki Oyun: {game}').format(game=game.chat.title)

    answer_async(context.bot, update.inline_query.id, results, cache_time=0,
                 switch_pm_text=switch, switch_pm_parameter='select')


@game_locales
@user_locale
def process_result(update: Update, context: CallbackContext):
    """
    Handler for chosen inline results.
    Checks the players actions and acts accordingly.
    """
    try:
        user = update.chosen_inline_result.from_user
        player = gm.userid_current[user.id]
        game = player.game
        result_id = update.chosen_inline_result.result_id
        chat = game.chat
    except (KeyError, AttributeError):
        return

    logger.debug("Axtarılan nəticə: " + result_id)

    result_id, anti_cheat = result_id.split(':')
    last_anti_cheat = player.anti_cheat
    player.anti_cheat += 1

    if result_id in ('hand', 'gameinfo', 'nogame'):
        return
    elif result_id.startswith('mode_'):
        # First 5 characters are 'mode_', the rest is the gamemode.
        mode = result_id[5:]
        game.set_mode(mode)
        logger.info("Oyun modu dəyişildi {mode}".format(mode = mode))
        send_async(context.bot, chat.id, text=__("Oyun modu dəyişildi {mode}".format(mode = mode)))
        return
    elif len(result_id) == 36:  # UUID result
        return
    elif int(anti_cheat) != last_anti_cheat:
        send_async(context.bot, chat.id,
                   text=__("Fırıldaq cəhdi edən {name}", multi=game.translate)
                   .format(name=display_name(player.user)))
        return
    elif result_id == 'call_bluff':
        do_call_bluff(context.bot, player)
    elif result_id == 'draw':
        do_draw(context.bot, player)
    elif result_id == 'pass':
        game.turn()
    elif result_id in c.COLORS:
        game.choose_color(result_id)
    else:
        do_play_card(context.bot, player, result_id)

    if game_is_running(game):
        nextplayer_message = (
            __("Növbəti oyunçu: {name}", multi=game.translate)
            .format(name=display_name(game.current_player.user)))
        choice = [[InlineKeyboardButton(text=_("Seçiminizi Edin!"), switch_inline_query_current_chat='')]]
        send_async(context.bot, chat.id,
                        text=nextplayer_message,
                        reply_markup=InlineKeyboardMarkup(choice))


# Add all handlers to the dispatcher and run the bot
dispatcher.add_handler(InlineQueryHandler(reply_to_query))
dispatcher.add_handler(ChosenInlineResultHandler(process_result, pass_job_queue=True))
# 🟢 Lobby (qeydiyyat menyusu) düymələri - catch-all select_game-dən ƏVVƏL
# qeydiyyatdan keçirilməlidir ki, öz callback_data-larını "oğurlamasın"
dispatcher.add_handler(CallbackQueryHandler(lobby_join_callback, pattern='^uno_lobby_join$'))
dispatcher.add_handler(CallbackQueryHandler(lobby_start_callback, pattern='^uno_lobby_start$'))
dispatcher.add_handler(CallbackQueryHandler(select_game))
dispatcher.add_handler(CommandHandler('start', start_game))
dispatcher.add_handler(CommandHandler(['new', 'uno'], new_game))
dispatcher.add_handler(CommandHandler('stop', kill_game))
dispatcher.add_handler(CommandHandler('join', join_game))
dispatcher.add_handler(CommandHandler('leave', leave_game))
dispatcher.add_handler(CommandHandler('open', open_game))
dispatcher.add_handler(CommandHandler('close', close_game))
dispatcher.add_handler(CommandHandler('enablelrme_translationss',
                                      enable_translations))
dispatcher.add_handler(CommandHandler('disableleme_translationss',
                                      disable_translations))
dispatcher.add_handler(CommandHandler('skip', skip_player))
dispatcher.add_handler(CommandHandler('notify_me', notify_me))
simple_commands.register()
settings.register()
broadcast.register()
dispatcher.add_handler(MessageHandler(Filters.status_update, status_update))
dispatcher.add_error_handler(error)

# 🟢 5 dəqiqədən bir başlamamış qeydiyyat (lobby) menyularını yoxlayır
# 🟢 5 dəqiqədən bir yox, hər 20 saniyədən bir yoxlanılır - həm qeydiyyat
# (lobby), həm də artıq başlamış hərəkətsiz oyunlar üçün YEGANƏ avtomatik
# bitirmə mexanizmi budur
updater.job_queue.run_repeating(check_inactive_lobbies_job, interval=20, first=20)

start_bot(updater)
updater.idle()
