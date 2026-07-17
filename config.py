#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
from dotenv import load_dotenv

load_dotenv()

# Bot token - .env faylından oxunur (serverdə: TOKEN=... yazılır)
TOKEN = os.getenv("TOKEN")
if not TOKEN:
    raise ValueError("TOKEN .env faylında və ya mühit dəyişənlərində tapılmadı!")

# MongoDB URL - .env faylından oxunur (serverdə: MONGO=... yazılır)
MONGO_URL = os.getenv("MONGO", "mongodb://localhost:27017")

# Sudo istifadəçilər (broadcast üçün) - vergüllə ayrılmış ID-lər
SUDO_USERS = os.getenv("SUDO_USERS", "").split(",")

# Bot parametrləri
WORKERS = int(os.getenv("WORKERS", 4))
ADMIN_LIST = []
OPEN_LOBBY = True
DEFAULT_GAMEMODE = "classic"
ENABLE_TRANSLATIONS = False
WAITING_TIME = 120

# Oyun limitləri
MIN_PLAYERS = 2
MAX_PLAYERS = 10

# Səviyyə sistemi: (tələb olunan ümumi xal, ad, emoji)
RANKS = [
    (0,      "Yeni Başlayan",  "🌱"),
    (50,     "Çavuş",         "⚔️"),
    (150,    "Cəngavər",      "🛡️"),
    (350,    "Usta",          "🎯"),
    (700,    "Qəhrəman",      "🦸"),
    (1200,   "Böyük Usta",    "🌟"),
    (2000,   "Əfsanə",        "👑"),
    (3000,   "Tanrı",         "🔱"),
    (5000,   "Ölümsüz",       "💎"),
    (8000,   "UNO Allahı",    "🏆"),
]

# Xal sistemi: oyundakı mövqeyə görə qazanılan xal
PLACE_POINTS = {
    1: 30,   # 1-ci yer
    2: 15,   # 2-ci yer
    3: 8,    # 3-cü yer
    4: 4,    # 4-cü yer
    5: 2,    # 5-ci yer
    6: 1,    # 6-cı yer
}
# 7+ yer üçün 0 xal

def get_rank(total_points):
    """Ümumi xala görə səviyyə nömrəsi, adı və emojini qaytarır"""
    level = 1
    rank_name = RANKS[0][1]
    rank_emoji = RANKS[0][2]
    for i, (req_points, name, emoji) in enumerate(RANKS):
        if total_points >= req_points:
            level = i + 1
            rank_name = name
            rank_emoji = emoji
        else:
            break
    return level, rank_name, rank_emoji
