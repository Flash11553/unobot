#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Telegram bot to play UNO in group chats
#
# ARTIQ Pony ORM/SQLite ƏVƏZİNƏ MongoDB istifadə olunur. Bu sinif köhnə
# Pony Entity ilə EYNİ İSTİFADƏ ÜSULUNU saxlayır ki, botun qalan hissəsi
# (settings.py, actions.py, internationalization.py, simple_commands.py)
# HEÇ DƏYİŞMƏDƏN işləməyə davam etsin:
#
#   UserSetting.get(id=user.id)   -> obyekt və ya None
#   UserSetting(id=user.id)       -> yeni qeyd yaradır və qaytarır
#   us.stats = True               -> DƏRHAL Mongo-ya yazılır
#   us.games_played += 1          -> DƏRHAL Mongo-ya yazılır
#
# QEYD: Bütün Mongo əməliyyatları try/except ilə əhatələnib ki, keçici bir
# şəbəkə/DB xətası oyunun əsas məntiqini (kart oynama, sıra keçmə və s.)
# yarımçıq kəsib "sıradan çıxarmasın" - xəta sadəcə log-a yazılır.

import logging

from database import db
from levels import compute_level

logger = logging.getLogger(__name__)

users_collection = db["user_settings"] if db is not None else None

_DEFAULT_LEVEL, _DEFAULT_RANK = compute_level(0)

DEFAULTS = {
    "lang": "",
    "stats": False,
    "first_places": 0,
    "games_played": 0,
    "cards_played": 0,
    "use_keyboards": False,
    "name": "",
    "level": _DEFAULT_LEVEL,
    "rank_name": _DEFAULT_RANK,
}


class UserSetting:
    """MongoDB-də saxlanılan istifadəçi ayarları/statistikası."""

    def __init__(self, id):
        doc = dict(DEFAULTS)
        doc["_id"] = id
        if users_collection is not None:
            try:
                users_collection.update_one(
                    {"_id": id}, {"$setOnInsert": doc}, upsert=True
                )
                fetched = users_collection.find_one({"_id": id})
                if fetched:
                    doc = fetched
            except Exception as e:
                logger.error(f"UserSetting yaradılarkən Mongo xətası (id={id}): {e}")
        self.__dict__["id"] = id
        for k, v in DEFAULTS.items():
            self.__dict__[k] = doc.get(k, v)

    @classmethod
    def get(cls, id):
        if users_collection is None:
            return None
        try:
            doc = users_collection.find_one({"_id": id})
        except Exception as e:
            logger.error(f"UserSetting oxunarkən Mongo xətası (id={id}): {e}")
            return None
        if not doc:
            return None
        obj = cls.__new__(cls)
        obj.__dict__["id"] = id
        for k, v in DEFAULTS.items():
            obj.__dict__[k] = doc.get(k, v)
        return obj

    def __setattr__(self, name, value):
        self.__dict__[name] = value

        if name == "id":
            return

        # Səviyyə/rütbə HƏMİŞƏ first_places-dən hesablanır - saxlanılan
        # dəyər sadəcə arayış/leaderboard üçün əlavə məlumatdır.
        if name == "first_places":
            level, rank_name = compute_level(value)
            self.__dict__["level"] = level
            self.__dict__["rank_name"] = rank_name

        if users_collection is None:
            return

        try:
            update = {"$set": {name: value}}
            if name == "first_places":
                update["$set"]["level"] = self.__dict__["level"]
                update["$set"]["rank_name"] = self.__dict__["rank_name"]
            users_collection.update_one({"_id": self.id}, update, upsert=True)
        except Exception as e:
            logger.error(f"UserSetting yazılarkən Mongo xətası (id={self.id}, sahə={name}): {e}")
