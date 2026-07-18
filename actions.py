import random

import logging

import card as c
from datetime import datetime

from telegram import Message, Chat
from telegram.ext import CallbackContext
from apscheduler.jobstores.base import JobLookupError

from config import TIME_REMOVAL_AFTER_SKIP, MIN_FAST_TURN_TIME
from errors import DeckEmptyError, NotEnoughPlayersError
from internationalization import __, _
from levels import compute_level, place_label
from shared_vars import gm
from user_setting import UserSetting
from utils import send_async, display_name, game_is_running

logger = logging.getLogger(__name__)

class Countdown(object):
    player = None
    job_queue = None

    def __init__(self, player, job_queue):
        self.player = player
        self.job_queue = job_queue


# TODO do_skip() could get executed in another thread (it can be a job), so it looks like it can't use game.translate?
def do_skip(bot, player, job_queue=None):
    game = player.game
    chat = game.chat
    skipped_player = game.current_player
    next_player = game.current_player.next

    if skipped_player.waiting_time > 0:
        skipped_player.anti_cheat += 1
        skipped_player.waiting_time -= TIME_REMOVAL_AFTER_SKIP
        if (skipped_player.waiting_time < 0):
            skipped_player.waiting_time = 0

        try:
            skipped_player.draw()
        except DeckEmptyError:
            pass

        n = skipped_player.waiting_time
        send_async(bot, chat.id,
                   text=__("Bu oyunçunu keçmək üçün vaxt"
                        "azaldı. {time} saniyə qaldı.\n"
                        "Növbəti oyunçu: {name}", multi=game.translate)
                   .format(time=n,
                           name=display_name(next_player.user))
        )
        logger.info("{player} keçildi! "
                    .format(player=display_name(player.user)))
        game.turn()
        if job_queue:
            start_player_countdown(bot, game, job_queue)

    else:
        ended = process_departure(bot, chat, game, skipped_player.user)

        if not ended:
            send_async(bot, chat.id,
                       text=__("{name1} vaxtı bitdi"
                            "və oyundan kənarlaşdırıldı!\n"
                            "Növbəti oyuçu: {name2}", multi=game.translate)
                       .format(name1=display_name(skipped_player.user),
                               name2=display_name(next_player.user)))
            logger.info("{player} keçildi! "
                    .format(player=display_name(player.user)))
            if job_queue:
                start_player_countdown(bot, game, job_queue)



def send_final_standings(bot, chat_id, game):
    """Domino botundakı kimi, oyun TAM bitəndə (son oyunçu da bitirəndə)
    hamının yerini (1-ci, 2-ci, 3-cü ...) səviyyə/rütbəsi ilə göstərir."""
    lines = []
    for i, finisher_user in enumerate(game.finish_order, start=1):
        us = UserSetting.get(id=finisher_user.id)
        wins = us.first_places if us else 0
        _level, rank_name = compute_level(wins)
        lines.append(
            f"{place_label(i)}: *{display_name(finisher_user)}* — {rank_name}"
        )

    result_message = (
        "🎉 *OYUN BAŞA ÇATDI!* 🎉\n\n" + "\n".join(lines)
    )
    send_async(bot, chat_id, text=result_message, parse_mode="Markdown")


def process_departure(bot, chat, game, user):
    """/leave və skip-lə kənarlaşdırma zamanı ORTAQ yer (placement) izləmə
    məntiqi. Oyunu tərk edən oyunçu HEÇ VAXT xal (qələbə) qazanmır və
    sıralamada HƏMİŞƏ ən pis yerlərdən birinə yazılır.

    Əgər bu tərk etmə oyunu TAM bitirirsə (yalnız 1 nəfər qalırsa), sağ
    qalan sonuncu oyunçu - tərk edəndən HƏMİŞƏ daha yaxşı yerdə olmaqla -
    sıralamaya əlavə olunur və əgər hələ heç kim (players_won == 0) oyunu
    bitirməyibsə, bu sağ qalan oyunçu 1-ci sayılır və +1 xal qazanır.

    Return: True -> oyun tam bitdi (final sıralama göndərildi)
            False -> oyun davam edir
    """
    try:
        gm.leave_game(user, chat)
    except NotEnoughPlayersError:
        last_player = game.current_player.user

        # Sağ qalan oyunçu, tərk edəndən HƏMİŞƏ daha yaxşı yerdə olur
        game.finish_order.append(last_player)
        game.finish_order.append(user)

        send_final_standings(bot, chat.id, game)

        us_last = UserSetting.get(id=last_player.id)
        if not us_last:
            us_last = UserSetting(id=last_player.id)
        us_last.games_played += 1
        us_last.name = display_name(last_player)
        if game.players_won == 0:
            us_last.first_places += 1

        us_dep = UserSetting.get(id=user.id)
        if not us_dep:
            us_dep = UserSetting(id=user.id)
        us_dep.games_played += 1
        us_dep.name = display_name(user)

        gm.end_game(chat, user)
        return True

    # Oyun davam edir - tərk edən oyunçu sıralamaya (indiki sona) yazılır,
    # xal qazanmır, amma oynadığı oyun sayına düşür
    game.finish_order.append(user)

    us_dep = UserSetting.get(id=user.id)
    if not us_dep:
        us_dep = UserSetting(id=user.id)
    us_dep.games_played += 1
    us_dep.name = display_name(user)

    return False


def do_play_card(bot, player, result_id):
    """Seçilmiş kartı masaya qoyur və ehtiyac olarsa, qrupa oyun vəziyyəti ilə bağlı məlumat göndərir."""
    card = c.from_str(result_id)
    player.play(card)
    game = player.game
    chat = game.chat
    user = player.user

    us = UserSetting.get(id=user.id)
    if not us:
        us = UserSetting(id=user.id)

    us.cards_played += 1

    if game.choosing_color:
        send_async(bot, chat.id, text=__("Zəhmət olmasa reng seçin", multi=game.translate))

    if len(player.cards) == 1:
        send_async(bot, chat.id, text="UNO!")

    if len(player.cards) == 0:
        place = len(game.finish_order) + 1
        game.finish_order.append(user)

        if place == 1:
            send_async(bot, chat.id,
                       text=__("🏆 {name} UNO edib qalib gəldi! (1-ci yer)", multi=game.translate)
                       .format(name=user.first_name))
        else:
            send_async(bot, chat.id,
                       text=__("🎉 {name} oyunu {place}-cü yerdə bitirdi!", multi=game.translate)
                       .format(name=user.first_name, place=place))

        us.games_played += 1
        us.name = display_name(user)

        if game.players_won == 0:
            us.first_places += 1

        game.players_won += 1

        try:
            gm.leave_game(user, chat)
        except NotEnoughPlayersError:
            last_player = game.current_player.user
            game.finish_order.append(last_player)

            send_final_standings(bot, chat.id, game)

            us2 = UserSetting.get(id=last_player.id)
            if not us2:
                us2 = UserSetting(id=last_player.id)
            us2.games_played += 1
            us2.name = display_name(last_player)

            gm.end_game(chat, user)


def do_draw(bot, player):
    """Kart çekir"""
    game = player.game
    draw_counter_before = game.draw_counter

    try:
        player.draw()
    except DeckEmptyError:
        send_async(bot, player.game.chat.id,
                   text=__("Əlinizdə kart qalmayıb artıq.",
                           multi=game.translate))

    if (game.last_card.value == c.DRAW_TWO or
        game.last_card.special == c.DRAW_FOUR) and \
            draw_counter_before > 0:
        game.turn()


def do_call_bluff(bot, player):
    """Blöfün yoxlanılmasını təmin edir"""
    game = player.game
    chat = game.chat

    if player.prev.bluffing:
        send_async(bot, chat.id,
                   text=__("Blöf aşkar olundu! 4 kart verilir oyunçuya: {name}",
                           multi=game.translate)
                   .format(name=player.prev.user.first_name))

        try:
            player.prev.draw()
        except DeckEmptyError:
            send_async(bot, player.game.chat.id,
                       text=__("Əlinizdə kart qalmayıb artıq.",
                               multi=game.translate))

    else:
        game.draw_counter += 2
        send_async(bot, chat.id,
                   text=__("{name1} Blöf etmə! 6 kart verilir oyunçuya: {name2}",
                           multi=game.translate)
                   .format(name1=player.prev.user.first_name,
                           name2=player.user.first_name))
        try:
            player.draw()
        except DeckEmptyError:
            send_async(bot, player.game.chat.id,
                       text=__("Əlinizdə kart qalmayıb artıq.",
                               multi=game.translate))

    game.turn()


def start_player_countdown(bot, game, job_queue):
    player = game.current_player
    time = player.waiting_time

    if time < MIN_FAST_TURN_TIME:
        time = MIN_FAST_TURN_TIME

    if game.mode == 'fast':
        if game.job:
            try:
                game.job.schedule_removal()
            except JobLookupError:
                pass

        job = job_queue.run_once(
            #lambda x,y: do_skip(bot, player),
            skip_job,
            time,
            context=Countdown(player, job_queue)
        )

        logger.info("Geri sayım başladı oyunçu üçün: {player}. {time} saniyə."
                    .format(player=display_name(player.user), time=time))
        player.game.job = job


def skip_job(context: CallbackContext):
    player = context.job.context.player
    game = player.game
    if game_is_running(game):
        job_queue = context.job.context.job_queue
        do_skip(context.bot, player, job_queue)
