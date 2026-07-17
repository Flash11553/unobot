#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Telegram bot to play UNO in group chats
# Copyright (c) 2016 Jannes Höke <uno@jhoeke.de>
# Licensed under AGPL v3

"""
Defines the cards and card-related functions for the UNO bot.
"""

from functools import total_ordering

COLORS = ['r', 'b', 'g', 'y']
COLOR_ICONS = {'r': '❤️', 'b': '💙', 'g': '💚', 'y': '💛'}

NUMBERS = [str(n) for n in range(10)] + [str(n) for n in range(1, 10)]
SPECIAL_CARD_TYPES = ['skip', 'reverse', 'draw_two']
WILD_CARD_TYPES = ['choose', 'draw_four']

SKIP = 'skip'
REVERSE = 'reverse'
DRAW_TWO = 'draw_two'
CHOOSE = 'choose'
DRAW_FOUR = 'draw_four'

STICKERS = {
    # Red cards
    'r0': 'CAACAgIAAxkBAAIBmWiMpAKbRTNbCdRAAeyv11a6z0yZAAI0AQACVS2tCg_8jFLFBh-iHgQ',
    'r1': 'CAACAgIAAxkBAAIBmmhMpAKMSpBAAeyv11a6z0yZAAI1AQACVS2tCg_8jFLFBh-iHgQ',
    'r2': 'CAACAgIAAxkBAAIBm2iMpAKNSpBAAeyv11a6z0yZAAI2AQACVS2tCg_8jFLFBh-iHgQ',
    'r3': 'CAACAgIAAxkBAAIBnGiMpAKOSpBAAeyv11a6z0yZAAI3AQACVS2tCg_8jFLFBh-iHgQ',
    'r4': 'CAACAgIAAxkBAAIBnWiMpAKPSpBAAeyv11a6z0yZAAI4AQACVS2tCg_8jFLFBh-iHgQ',
    'r5': 'CAACAgIAAxkBAAIBnmiMpAKQSpBAAeyv11a6z0yZAAI5AQACVS2tCg_8jFLFBh-iHgQ',
    'r6': 'CAACAgIAAxkBAAIBn2iMpAKRSpBAAeyv11a6z0yZAAI6AQACVS2tCg_8jFLFBh-iHgQ',
    'r7': 'CAACAgIAAxkBAAIBoGiMpAKSSpBAAeyv11a6z0yZAAI7AQACVS2tCg_8jFLFBh-iHgQ',
    'r8': 'CAACAgIAAxkBAAIBoWiMpAKTSpBAAeyv11a6z0yZAAI8AQACVS2tCg_8jFLFBh-iHgQ',
    'r9': 'CAACAgIAAxkBAAIBomiMpAKUSpBAAeyv11a6z0yZAAI9AQACVS2tCg_8jFLFBh-iHgQ',
    'rskip': 'CAACAgIAAxkBAAIBo2iMpAKVSpBAAeyv11a6z0yZAAI-AQACVS2tCg_8jFLFBh-iHgQ',
    'rreverse': 'CAACAgIAAxkBAAIBpGiMpAKWSpBAAeyv11a6z0yZAAI_AQACVS2tCg_8jFLFBh-iHgQ',
    'rdraw_two': 'CAACAgIAAxkBAAIBpWiMpAKXSpBAAeyv11a6z0yZAAJAAQACVS2tCg_8jFLFBh-iHgQ',
    # Blue cards
    'b0': 'CAACAgIAAxkBAAIBpmiMpAKYSpBAAeyv11a6z0yZAAJBAQACVS2tCg_8jFLFBh-iHgQ',
    'b1': 'CAACAgIAAxkBAAIBp2iMpAKZSpBAAeyv11a6z0yZAAJCAQACVS2tCg_8jFLFBh-iHgQ',
    'b2': 'CAACAgIAAxkBAAIBqGiMpAKaSpBAAeyv11a6z0yZAAJDAQACVS2tCg_8jFLFBh-iHgQ',
    'b3': 'CAACAgIAAxkBAAIBqWiMpAKbSpBAAeyv11a6z0yZAAJEAQACVS2tCg_8jFLFBh-iHgQ',
    'b4': 'CAACAgIAAxkBAAIBqmiMpAKcSpBAAeyv11a6z0yZAAJFAQACVS2tCg_8jFLFBh-iHgQ',
    'b5': 'CAACAgIAAxkBAAIBq2iMpAKdSpBAAeyv11a6z0yZAAJGAQACVS2tCg_8jFLFBh-iHgQ',
    'b6': 'CAACAgIAAxkBAAIBrGiMpAKeSpBAAeyv11a6z0yZAAJHAQACVS2tCg_8jFLFBh-iHgQ',
    'b7': 'CAACAgIAAxkBAAIBrWiMpAKfSpBAAeyv11a6z0yZAAJIAQACVS2tCg_8jFLFBh-iHgQ',
    'b8': 'CAACAgIAAxkBAAIBrmiMpAKgSpBAAeyv11a6z0yZAAJJAQACVS2tCg_8jFLFBh-iHgQ',
    'b9': 'CAACAgIAAxkBAAIBr2iMpAKhSpBAAeyv11a6z0yZAAJKAQACVS2tCg_8jFLFBh-iHgQ',
    'bskip': 'CAACAgIAAxkBAAIBsGiMpAKiSpBAAeyv11a6z0yZAAJLAQACVS2tCg_8jFLFBh-iHgQ',
    'breverse': 'CAACAgIAAxkBAAIBsWiMpAKjSpBAAeyv11a6z0yZAAJMAQACVS2tCg_8jFLFBh-iHgQ',
    'bdraw_two': 'CAACAgIAAxkBAAIBsmiMpAKkSpBAAeyv11a6z0yZAAJNAQACVS2tCg_8jFLFBh-iHgQ',
    # Green cards
    'g0': 'CAACAgIAAxkBAAIBs2iMpAKlSpBAAeyv11a6z0yZAAJOAQACVS2tCg_8jFLFBh-iHgQ',
    'g1': 'CAACAgIAAxkBAAIBtGiMpAKmSpBAAeyv11a6z0yZAAJPAQACVS2tCg_8jFLFBh-iHgQ',
    'g2': 'CAACAgIAAxkBAAIBtWiMpAKnSpBAAeyv11a6z0yZAAJQAQACVS2tCg_8jFLFBh-iHgQ',
    'g3': 'CAACAgIAAxkBAAIBtmiMpAKoSpBAAeyv11a6z0yZAAJRAQACVS2tCg_8jFLFBh-iHgQ',
    'g4': 'CAACAgIAAxkBAAIBt2iMpAKpSpBAAeyv11a6z0yZAAJSAQACVS2tCg_8jFLFBh-iHgQ',
    'g5': 'CAACAgIAAxkBAAIBuGiMpAKqSpBAAeyv11a6z0yZAAJTAQACVS2tCg_8jFLFBh-iHgQ',
    'g6': 'CAACAgIAAxkBAAIBuWiMpAKrSpBAAeyv11a6z0yZAAJUAQACVS2tCg_8jFLFBh-iHgQ',
    'g7': 'CAACAgIAAxkBAAIBumiMpAKsSpBAAeyv11a6z0yZAAJVAQACVS2tCg_8jFLFBh-iHgQ',
    'g8': 'CAACAgIAAxkBAAIBu2iMpAKtSpBAAeyv11a6z0yZAAJWAQACVS2tCg_8jFLFBh-iHgQ',
    'g9': 'CAACAgIAAxkBAAIBvGiMpAKuSpBAAeyv11a6z0yZAAJXAQACVS2tCg_8jFLFBh-iHgQ',
    'gskip': 'CAACAgIAAxkBAAIBvWiMpAKvSpBAAeyv11a6z0yZAAJYAQACVS2tCg_8jFLFBh-iHgQ',
    'greverse': 'CAACAgIAAxkBAAIBvmiMpAKwSpBAAeyv11a6z0yZAAJZAQACVS2tCg_8jFLFBh-iHgQ',
    'gdraw_two': 'CAACAgIAAxkBAAIBv2iMpAKxSpBAAeyv11a6z0yZAAJaAQACVS2tCg_8jFLFBh-iHgQ',
    # Yellow cards
    'y0': 'CAACAgIAAxkBAAIBwGiMpAKySpBAAeyv11a6z0yZAAJbAQACVS2tCg_8jFLFBh-iHgQ',
    'y1': 'CAACAgIAAxkBAAIBwWiMpAKzSpBAAeyv11a6z0yZAAJcAQACVS2tCg_8jFLFBh-iHgQ',
    'y2': 'CAACAgIAAxkBAAIBwmiMpAK0SpBAAeyv11a6z0yZAAJdAQACVS2tCg_8jFLFBh-iHgQ',
    'y3': 'CAACAgIAAxkBAAIBw2iMpAK1SpBAAeyv11a6z0yZAAJeAQACVS2tCg_8jFLFBh-iHgQ',
    'y4': 'CAACAgIAAxkBAAIBxGiMpAK2SpBAAeyv11a6z0yZAAJfAQACVS2tCg_8jFLFBh-iHgQ',
    'y5': 'CAACAgIAAxkBAAIBxWiMpAK3SpBAAeyv11a6z0yZAAJgAQACVS2tCg_8jFLFBh-iHgQ',
    'y6': 'CAACAgIAAxkBAAIBxmiMpAK4SpBAAeyv11a6z0yZAAJhAQACVS2tCg_8jFLFBh-iHgQ',
    'y7': 'CAACAgIAAxkBAAIBx2iMpAK5SpBAAeyv11a6z0yZAAJiAQACVS2tCg_8jFLFBh-iHgQ',
    'y8': 'CAACAgIAAxkBAAIByGiMpAK6SpBAAeyv11a6z0yZAAJjAQACVS2tCg_8jFLFBh-iHgQ',
    'y9': 'CAACAgIAAxkBAAIBy2iMpAK7SpBAAeyv11a6z0yZAAJkAQACVS2tCg_8jFLFBh-iHgQ',
    'yskip': 'CAACAgIAAxkBAAIBzGiMpAK8SpBAAeyv11a6z0yZAAJlAQACVS2tCg_8jFLFBh-iHgQ',
    'yreverse': 'CAACAgIAAxkBAAIBzWiMpAK9SpBAAeyv11a6z0yZAAJmAQACVS2tCg_8jFLFBh-iHgQ',
    'ydraw_two': 'CAACAgIAAxkBAAIBzmiMpAK-SpBAAeyv11a6z0yZAAJnAQACVS2tCg_8jFLFBh-iHgQ',
    # Wild cards
    'choose': 'CAACAgIAAxkBAAIBz2iMpAK_SpBAAeyv11a6z0yZAAJoAQACVS2tCg_8jFLFBh-iHgQ',
    'draw_four': 'CAACAgIAAxkBAAIB0GiMpALASpBAAeyv11a6z0yZAAJpAQACVS2tCg_8jFLFBh-iHgQ',
    # Option stickers
    'option_draw': 'CAACAgIAAxkBAAIB0WiMpALBSpBAAeyv11a6z0yZAAJqAQACVS2tCg_8jFLFBh-iHgQ',
    'option_pass': 'CAACAgIAAxkBAAIB0miMpALCSpBAAeyv11a6z0yZAAJrAQACVS2tCg_8jFLFBh-iHgQ',
    'option_bluff': 'CAACAgIAAxkBAAIB02iMpALDSpBAAeyv11a6z0yZAAJsAQACVS2tCg_8jFLFBh-iHgQ',
    'option_info': 'CAACAgIAAxkBAAIB1GiMpALESpBAAeyv11a6z0yZAAJtAQACVS2tCg_8jFLFBh-iHgQ',
}

# Grey (unplayable) stickers - same file_ids but grey version
# In production, these would be different file_ids. Using same for now.
STICKERS_GREY = {k: v for k, v in STICKERS.items()}


@total_ordering
class Card(object):
    """Represents a single UNO card"""

    def __init__(self, color, value, special=None):
        self.color = color
        self.value = value
        self.special = special

    def __str__(self):
        if self.special:
            return self.special
        return self.color + self.value

    def __repr__(self):
        color_icon = COLOR_ICONS.get(self.color, '') if self.color else ''
        if self.special == CHOOSE:
            return f'Rəng Seçici 🌈'
        if self.special == DRAW_FOUR:
            return f'+4 🌈'
        value_repr = {
            SKIP: 'Atla',
            REVERSE: 'Çevir',
            DRAW_TWO: '+2',
        }.get(self.value, self.value)
        return f'{color_icon} {value_repr}'

    def __eq__(self, other):
        if other is None:
            return False
        return str(self) == str(other)

    def __lt__(self, other):
        return str(self) < str(other)

    def __hash__(self):
        return hash(str(self))
