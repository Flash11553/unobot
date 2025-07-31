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

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ParseMode, Update
from telegram.ext import (
    CallbackContext,
    CallbackQueryHandler,
    ChosenInlineResultHandler,
    CommandHandler,
    Filters,
    InlineQueryHandler,
    MessageHandler,
)
from telegram.ext.dispatcher import run_async

import card as c
import settings
import simple_commands
from actions import (
    do_call_bluff,
    do_draw,
    do_play_card,
    do_skip,
    start_player_countdown,
)
from config import DEFAULT_GAMEMODE, MIN_PLAYERS, WAITING_TIME
from errors import (
    AlreadyJoinedError,
    DeckEmptyError,
    LobbyClosedError,
    NoGameInChatError,
    NotEnoughPlayersError,
)
from internationalization import _, __, game_locales, user_locale
from results import (
    add_call_bluff,
    add_card,
    add_choose_color,
    add_draw,
    add_gameinfo,
    add_mode_classic,
    add_mode_fast,
    add_mode_text,
    add_mode_wild,
    add_no_game,
    add_not_started,
    add_other_cards,
    add_pass,
)
from shared_vars import dispatcher, gm, updater
from simple_commands import help_handler
from start_bot import start_bot
from utils import (
    TIMEOUT,
    answer_async,
    display_name,
    error,
    game_is_running,
    send_async,
    user_is_creator,
    user_is_creator_or_admin,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)
logging.getLogger("apscheduler").setLevel(logging.WARNING)


@user_locale
def notify_me(update: Update, context: CallbackContext):
    """Handler for /notify_me command, pm people for next game"""
    chat_id = update.message.chat_id
    if update.message.chat.type == "private":
        send_async(
            bot,
            chat_id,
            text=_(
                "Send this command in a group to be notified "
                "when a new game is started there."
            ),
        )
    else:
        try:
            gm.remind_dict[chat_id].add(update.message.from_user.id)
        except KeyError:
            gm.remind_dict[chat_id] = {update.message.from_user.id}


@user_locale
def new_game(update: Update, context: CallbackContext):
    """Handler for the /new command"""
    chat_id = update.message.chat_id

    if update.message.chat.type == "private":
        help_handler(update, context)

    else:

        if update.message.chat_id in gm.remind_dict:
            for user in gm.remind_dict[update.message.chat_id]:
                send_async(
                    context.bot,
                    user,
                    text=_("A new game has been started in {title}").format(
                        title=update.message.chat.title
                    ),
                )

            del gm.remind_dict[update.message.chat_id]

        game = gm.new_game(update.message.chat)
        game.starter = update.message.from_user
        game.owner.add(update.message.from_user.id)
        game.mode = DEFAULT_GAMEMODE
        send_async(
            context.bot,
            chat_id,
            text=_(
                "Created a new game! Join the game with /join "
                "and start the game with /start"
            ),
        )


@user_locale
def kill_game(update: Update, context: CallbackContext):
    """Handler for the /kill command"""
    chat = update.message.chat
    user = update.message.from_user
    games = gm.chatid_games.get(chat.id)

    if update.message.chat.type == "private":
        help_handler(update, context)
        return

    if not games:
        send_async(
            context.bot, chat.id, text=_("There is no running game in this chat.")
        )
        return

    game = games[-1]

    if user_is_creator_or_admin(user, game, context.bot, chat):

        try:
            gm.end_game(chat, user)
            send_async(
                context.bot, chat.id, text=__("Game ended!", multi=game.translate)
            )

        except NoGameInChatError:
            send_async(
                context.bot,
                chat.id,
                text=_(
                    "The game is not started yet. "
                    "Join the game with /join and start the game with /start"
                ),
                reply_to_message_id=update.message.message_id,
            )

    else:
        send_async(
            context.bot,
            chat.id,
            text=_("Only the game creator ({name}) and admin can do that.").format(
                name=game.starter.first_name
            ),
            reply_to_message_id=update.message.message_id,
        )


@user_locale
def join_game(update: Update, context: CallbackContext):
    """Handler for the /join command"""
    chat = update.message.chat

    if update.message.chat.type == "private":
        help_handler(update, context)
        return

    try:
        gm.join_game(update.message.from_user, chat)

    except LobbyClosedError:
        send_async(context.bot, chat.id, text=_("The lobby is closed"))

    except NoGameInChatError:
        send_async(
            context.bot,
            chat.id,
            text=_("No game is running at the moment. " "Create a new game with /new"),
            reply_to_message_id=update.message.message_id,
        )

    except AlreadyJoinedError:
        send_async(
            context.bot,
            chat.id,
            text=_("You already joined the game. Start the game " "with /start"),
            reply_to_message_id=update.message.message_id,
        )

    except DeckEmptyError:
        send_async(
            context.bot,
            chat.id,
            text=_(
                "There are not enough cards left in the deck for "
                "new players to join."
            ),
            reply_to_message_id=update.message.message_id,
        )

    else:
        send_async(
            context.bot,
            chat.id,
            text=_("Joined the game"),
            reply_to_message_id=update.message.message_id,
        )


@user_locale
def leave_game(update: Update, context: CallbackContext):
    """Handler for the /leave command"""
    chat = update.message.chat
    user = update.message.from_user

    player = gm.player_for_user_in_chat(user, chat)

    if player is None:
        send_async(
            context.bot,
            chat.id,
            text=_("You are not playing in a game in " "this group."),
            reply_to_message_id=update.message.message_id,
        )
        return

    game = player.game
    user = update.message.from_user

    try:
        gm.leave_game(user, chat)

    except NoGameInChatError:
        send_async(
            context.bot,
            chat.id,
            text=_("You are not playing in a game in " "this group."),
            reply_to_message_id=update.message.message_id,
        )

    except NotEnoughPlayersError:
        gm.end_game(chat, user)
        send_async(context.bot, chat.id, text=__("Game ended!", multi=game.translate))

    else:
        if game.started:
            send_async(
                context.bot,
                chat.id,
                text=__("Okay. Next Player: {name}", multi=game.translate).format(
                    name=display_name(game.current_player.user)
                ),
                reply_to_message_id=update.message.message_id,
            )
        else:
            send_async(
                context.bot,
                chat.id,
                text=__(
                    "{name} left the game before it started.", multi=game.translate
                ).format(name=display_name(user)),
                reply_to_message_id=update.message.message_id,
            )


@user_locale
def kick_player(update: Update, context: CallbackContext):
    """Handler for the /kick command"""

    if update.message.chat.type == "private":
        help_handler(update, context)
        return

    chat = update.message.chat
    user = update.message.from_user

    try:
        game = gm.chatid_games[chat.id][-1]

    except (KeyError, IndexError):
        send_async(
            context.bot,
            chat.id,
            text=_("No game is running at the moment. " "Create a new game with /new"),
            reply_to_message_id=update.message.message_id,
        )
        return

    if not game.started:
        send_async(
            context.bot,
            chat.id,
            text=_(
                "The game is not started yet. "
                "Join the game with /join and start the game with /start"
            ),
            reply_to_message_id=update.message.message_id,
        )
        return

    if user_is_creator_or_admin(user, game, context.bot, chat):

        if update.message.reply_to_message:
            kicked = update.message.reply_to_message.from_user

            try:
                gm.leave_game(kicked, chat)

            except NoGameInChatError:
                send_async(
                    context.bot,
                    chat.id,
                    text=_(
                        "Player {name} is not found in the current game.".format(
                            name=display_name(kicked)
                        )
                    ),
                    reply_to_message_id=update.message.message_id,
                )
                return

            except NotEnoughPlayersError:
                gm.end_game(chat, user)
                send_async(
                    context.bot,
                    chat.id,
                    text=_(
                        "{0} was kicked by {1}".format(
                            display_name(kicked), display_name(user)
                        )
                    ),
                )
                send_async(
                    context.bot, chat.id, text=__("Game ended!", multi=game.translate)
                )
                return

            send_async(
                context.bot,
                chat.id,
                text=_(
                    "{0} was kicked by {1}".format(
                        display_name(kicked), display_name(user)
                    )
                ),
            )

        else:
            send_async(
                context.bot,
                chat.id,
                text=_(
                    "Please reply to the person you want to kick and type /kick again."
                ),
                reply_to_message_id=update.message.message_id,
            )
            return

        send_async(
            context.bot,
            chat.id,
            text=__("Okay. Next Player: {name}", multi=game.translate).format(
                name=display_name(game.current_player.user)
            ),
            reply_to_message_id=update.message.message_id,
        )

    else:
        send_async(
            context.bot,
            chat.id,
            text=_("Only the game creator ({name}) and admin can do that.").format(
                name=game.starter.first_name
            ),
            reply_to_message_id=update.message.message_id,
        )


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
        send_async(
            bot, update.callback_query.message.chat_id, text=_("Game not found.")
        )
        return

    def selected():
        back = [
            [InlineKeyboardButton(text=_("Back to last group"), switch_inline_query="")]
        ]
        context.bot.answerCallbackQuery(
            update.callback_query.id,
            text=_("Please switch to the group you selected!"),
            show_alert=False,
            timeout=TIMEOUT,
        )

        context.bot.editMessageText(
            chat_id=update.callback_query.message.chat_id,
            message_id=update.callback_query.message.message_id,
            text=_(
                "Selected group: {group}\n"
                "<b>Make sure that you switch to the correct "
                "group!</b>"
            ).format(group=gm.userid_current[user_id].game.chat.title),
            reply_markup=InlineKeyboardMarkup(back),
            parse_mode=ParseMode.HTML,
            timeout=TIMEOUT,
        )

    dispatcher.run_async(selected)


@game_locales
def status_update(update: Update, context: CallbackContext):
    """Remove player from game if user leaves the group"""
    chat = update.message.chat

    if update.message.left_chat_member:
        user = update.message.left_chat_member

        try:
            gm.leave_game(user, chat)
            game = gm.player_for_user_in_chat(user, chat).game

        except NoGameInChatError:
            pass
        except NotEnoughPlayersError:
            gm.end_game(chat, user)
            send_async(
                context.bot, chat.id, text=__("Game ended!", multi=game.translate)
            )
        else:
            send_async(
                context.bot,
                chat.id,
                text=__("Removing {name} from the game", multi=game.translate).format(
                    name=display_name(user)
                ),
            )


@game_locales
@user_locale
def start_game(update: Update, context: CallbackContext):
    """Handler for the /start command"""

    if update.message.chat.type != "private":
        chat = update.message.chat

        try:
            game = gm.chatid_games[chat.id][-1]
        except (KeyError, IndexError):
            send_async(
                context.bot,
                chat.id,
                text=_(
                    "There is no game running in this chat. Create "
                    "a new one with /new"
                ),
            )
            return

        if game.started:
            send_async(context.bot, chat.id, text=_("The game has already started"))

        elif len(game.players) < MIN_PLAYERS:
            send_async(
                context.bot,
                chat.id,
                text=__(
                    "At least {minplayers} players must /join the game "
                    "before you can start it"
                ).format(minplayers=MIN_PLAYERS),
            )

        else:
            # Starting a game
            game.start()

            for player in game.players:
                player.draw_first_hand()
            choice = [
                [
                    InlineKeyboardButton(
                        text=_("Make your choice!"), switch_inline_query_current_chat=""
                    )
                ]
            ]
            first_message = __(
                "First player: {name}\n"
                "Use /close to stop people from joining the game.\n"
                "Enable multi-translations with /enable_translations",
                multi=game.translate,
            ).format(name=display_name(game.current_player.user))

            def send_first():
                """Send the first card and player"""

                context.bot.sendSticker(
                    chat.id, sticker=c.STICKERS[str(game.last_card)], timeout=TIMEOUT
                )

                context.bot.sendMessage(
                    chat.id,
                    text=first_message,
                    reply_markup=InlineKeyboardMarkup(choice),
                    timeout=TIMEOUT,
                )

            dispatcher.run_async(send_first)
            start_player_countdown(context.bot, game, context.job_queue)

    elif len(context.args) and context.args[0] == "select":
        players = gm.userid_players[update.message.from_user.id]

        groups = list()
        for player in players:
            title = player.game.chat.title

            if player == gm.userid_current[update.message.from_user.id]:
                title = "- %s -" % player.game.chat.title

            groups.append(
                [
                    InlineKeyboardButton(
                        text=title, callback_data=str(player.game.chat.id)
                    )
                ]
            )

        send_async(
            context.bot,
            update.message.chat_id,
            text=_("Please select the group you want to play in."),
            reply_markup=InlineKeyboardMarkup(groups),
        )

    else:
        help_handler(update, context)


@user_locale
def close_game(update: Update, context: CallbackContext):
    """Handler for the /close command"""
    chat = update.message.chat
    user = update.message.from_user
    games = gm.chatid_games.get(chat.id)

    if not games:
        send_async(
            context.bot, chat.id, text=_("There is no running game in this chat.")
        )
        return

    game = games[-1]

    if user.id in game.owner:
        game.open = False
        send_async(
            context.bot,
            chat.id,
            text=_("Closed the lobby. " "No more players can join this game."),
        )
        return

    else:
        send_async(
            context.bot,
            chat.id,
            text=_("Only the game creator ({name}) and admin can do that.").format(
                name=game.starter.first_name
            ),
            reply_to_message_id=update.message.message_id,
        )
        return


@user_locale
def open_game(update: Update, context: CallbackContext):
    """Handler for the /open command"""
    chat = update.message.chat
    user = update.message.from_user
    games = gm.chatid_games.get(chat.id)

    if not games:
        send_async(
            context.bot, chat.id, text=_("There is no running game in this chat.")
        )
        return

    game = games[-1]

    if user.id in game.owner:
        game.open = True
        send_async(
            context.bot,
            chat.id,
            text=_("Opened the lobby. " "New players may /join the game."),
        )
        return
    else:
        send_async(
            context.bot,
            chat.id,
            text=_("Only the game creator ({name}) and admin can do that.").format(
                name=game.starter.first_name
            ),
            reply_to_message_id=update.message.message_id,
        )
        return


@user_locale
def enable_translations(update: Update, context: CallbackContext):
    """Handler for the /enable_translations command"""
    chat = update.message.chat
    user = update.message.from_user
    games = gm.chatid_games.get(chat.id)

    if not games:
        send_async(
            context.bot, chat.id, text=_("There is no running game in this chat.")
        )
        return

    game = games[-1]

    if user.id in game.owner:
        game.translate = True
        send_async(
            context.bot,
            chat.id,
            text=_("Enabled multi-translations. " "Disable with /disable_translations"),
        )
        return

    else:
    send_async(
        context.bot,
        chat.id,
        text=_("Only the game creator ({name}) and admin can do that.").format(
            name=game.starter.first_name
        ),
        reply_to_message_id=update.message.message_id,
    )
