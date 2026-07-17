#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MongoDB ilə bağlı bütün əməliyyatlar bu faylda saxlanılır.
- Broadcast üçün qrup/istifadəçi yaddaşı (heç vaxt silinmir)
- Oyunçu profili, reytinq, xal, səviyyə sistemi
"""

import logging
from pymongo import MongoClient, DESCENDING
from config import MONGO_URL, get_rank, PLACE_POINTS

logger = logging.getLogger(__name__)

# ─── MongoDB Bağlantısı ───────────────────────────────────────────────────────
try:
    _client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=5000)
    _db = _client["uno_bot_db"]

    chats_col    = _db["chats"]       # Broadcast qrupları
    users_col    = _db["users"]       # Broadcast istifadəçiləri
    profiles_col = _db["profiles"]    # Oyunçu profili (xal, səviyyə, statistika)

    # İndekslər — sürət üçün
    chats_col.create_index("chat_id", unique=True)
    users_col.create_index("user_id", unique=True)
    profiles_col.create_index("user_id", unique=True)
    profiles_col.create_index([("total_points", DESCENDING)])

    logger.info("✅ MongoDB bağlantısı uğurlu — uno_bot_db")
except Exception as exc:
    logger.error(f"❌ MongoDB bağlantı xətası: {exc}")
    chats_col = users_col = profiles_col = None


# ─── Broadcast: Qruplar ───────────────────────────────────────────────────────

def add_served_chat(chat_id: int):
    """Qrubu MongoDB-yə əlavə edir. Artıq varsa yenidən yazmir. Heç vaxt silinmir."""
    if chats_col is None:
        return
    try:
        chats_col.update_one(
            {"chat_id": chat_id},
            {"$setOnInsert": {"chat_id": chat_id}},
            upsert=True
        )
    except Exception as e:
        logger.warning(f"add_served_chat xətası: {e}")


def get_served_chats() -> list:
    """Bütün saxlanılmış qrupları qaytarır."""
    if chats_col is None:
        return []
    try:
        return list(chats_col.find({}, {"_id": 0, "chat_id": 1}))
    except Exception:
        return []


# ─── Broadcast: İstifadəçilər ─────────────────────────────────────────────────

def add_served_user(user_id: int):
    """İstifadəçini MongoDB-yə əlavə edir. Heç vaxt silinmir."""
    if users_col is None:
        return
    try:
        users_col.update_one(
            {"user_id": user_id},
            {"$setOnInsert": {"user_id": user_id}},
            upsert=True
        )
    except Exception as e:
        logger.warning(f"add_served_user xətası: {e}")


def get_served_users() -> list:
    """Bütün saxlanılmış istifadəçiləri qaytarır."""
    if users_col is None:
        return []
    try:
        return list(users_col.find({}, {"_id": 0, "user_id": 1}))
    except Exception:
        return []


# ─── Oyunçu Profili ───────────────────────────────────────────────────────────

def _get_or_create_profile(user_id: int, name: str) -> dict:
    """Profili qaytarır; yoxdursa yaradır."""
    doc = profiles_col.find_one({"user_id": user_id})
    if not doc:
        doc = {
            "user_id": user_id,
            "name": name,
            "total_points": 0,
            "games_played": 0,
            "wins": 0,           # 1-ci yer sayı
        }
        profiles_col.insert_one(doc)
    return doc


def record_game_result(user_id: int, name: str, place: int):
    """
    Oyun bitdikdən sonra hər oyunçunun nəticəsini MongoDB-yə yazır.
    place: 1 = qalib, 2 = ikinci, ...
    """
    if profiles_col is None:
        return
    try:
        points = PLACE_POINTS.get(place, 0)
        inc_data = {
            "total_points": points,
            "games_played": 1,
        }
        if place == 1:
            inc_data["wins"] = 1

        profiles_col.update_one(
            {"user_id": user_id},
            {
                "$inc": inc_data,
                "$set": {"name": name},
                "$setOnInsert": {"user_id": user_id},
            },
            upsert=True
        )
    except Exception as e:
        logger.warning(f"record_game_result xətası: {e}")


def get_profile(user_id: int) -> dict | None:
    """Oyunçunun profilini qaytarır."""
    if profiles_col is None:
        return None
    try:
        return profiles_col.find_one({"user_id": user_id})
    except Exception:
        return None


def get_top_ratings(limit: int = 25) -> list:
    """Ən çox xal qazanmış oyunçuları qaytarır."""
    if profiles_col is None:
        return []
    try:
        return list(
            profiles_col.find({}, {"_id": 0})
            .sort("total_points", DESCENDING)
            .limit(limit)
        )
    except Exception:
        return []


# ─── Broadcast Xəta Logu ─────────────────────────────────────────────────────

def log_broadcast_error(kind: str, entity_id: int, error_msg: str):
    filename = "errors_chats.txt" if kind == "chat" else "errors_users.txt"
    try:
        with open(filename, "a", encoding="utf-8") as f:
            f.write(f"🆔 {entity_id} | ❌ {error_msg}\n")
    except Exception:
        pass
