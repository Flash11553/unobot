#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Telegram bot to play UNO in group chats
# Copyright (c) 2016 Jannes Höke <uno@jhoeke.de>
# Licensed under AGPL v3

import random
from errors import DeckEmptyError
import card as c


class Deck(object):
    def __init__(self):
        self.cards = list()
        self.graveyard = list()

    def _fill_classic_(self):
        """Fill the deck with a standard UNO deck"""
        self.cards = list()
        for color in c.COLORS:
            # 0 appears once, 1-9 appear twice
            self.cards.append(c.Card(color, '0'))
            for value in c.NUMBERS[1:]:
                self.cards.append(c.Card(color, value))
            # Skip, Reverse, Draw Two × 2 each
            for _ in range(2):
                for special in c.SPECIAL_CARD_TYPES:
                    self.cards.append(c.Card(color, special))
        # Wild cards × 4 each
        for _ in range(4):
            self.cards.append(c.Card(None, None, c.CHOOSE))
            self.cards.append(c.Card(None, None, c.DRAW_FOUR))
        random.shuffle(self.cards)

    def _fill_wild_(self):
        """Fill deck with wild mode (more specials)"""
        self.cards = list()
        for color in c.COLORS:
            self.cards.append(c.Card(color, '0'))
            for value in ['1', '2', '3', '4', '5']:
                self.cards.append(c.Card(color, value))
            for _ in range(3):
                for special in c.SPECIAL_CARD_TYPES:
                    self.cards.append(c.Card(color, special))
        for _ in range(8):
            self.cards.append(c.Card(None, None, c.CHOOSE))
            self.cards.append(c.Card(None, None, c.DRAW_FOUR))
        random.shuffle(self.cards)

    def draw(self):
        """Draw a card from the deck"""
        try:
            return self.cards.pop()
        except IndexError:
            if self.graveyard:
                self.cards = self.graveyard
                self.graveyard = list()
                random.shuffle(self.cards)
                return self.cards.pop()
            else:
                raise DeckEmptyError()

    def dismiss(self, card):
        """Add a card to the graveyard"""
        if card:
            self.graveyard.append(card)
