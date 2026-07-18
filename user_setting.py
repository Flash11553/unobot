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
# Əlavə olaraq "level" və "rank_name" sahələri saxlanılır və hər dəfə
# first_places (qələbə sayı) dəyişəndə avtomatik yenidən hesablanır.

from database import db
from levels import compute_level

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
            users_collection.update_one(
                {"_id": id}, {"$setOnInsert": doc}, upsert=True
            )
            doc = users_collection.find_one({"_id": id}) or doc
        self.__dict__["id"] = id
        for k, v in DEFAULTS.items():
            self.__dict__[k] = doc.get(k, v)

    @classmethod
    def get(cls, id):
        if users_collection is None:
            return None
        doc = users_collection.find_one({"_id": id})
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

        if users_collection is not None:
            users_collection.update_one(
                {"_id": self.id}, {"$set": {name: value}}, upsert=True
            )

        # Qələbə sayı dəyişəndə səviyyə/rütbəni avtomatik yenilə
        if name == "first_places":
            level, rank_name = compute_level(value)
            if (level != self.__dict__.get("level") or
                    rank_name != self.__dict__.get("rank_name")):
                self.__dict__["level"] = level
                self.__dict__["rank_name"] = rank_name
                if users_collection is not None:
                    users_collection.update_one(
                        {"_id": self.id},
                        {"$set": {"level": level, "rank_name": rank_name}},
                        upsert=True,
                    )
