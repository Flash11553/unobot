#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Telegram bot to play UNO in group chats
#
# Bütün məlumatlar (istifadəçi statistikası, reytinq, broadcast siyahıları)
# artıq SQLite/Pony ƏVƏZİNƏ MongoDB-də saxlanılır. Bağlantı sətri koda
# YAZILMIR - serverdə .env faylında MONGO dəyişəni kimi verilir:
#
#   TOKEN=xxxxx
#   MONGO=mongodb+srv://user:pass@host/?appName=...
#
# Bu fayl botun hər yerindən "from database import db" ilə istifadə
# edilən tək MongoDB bağlantısını yaradır.

import logging

from pymongo import MongoClient

from config import MONGO_URL

logger = logging.getLogger(__name__)

db = None

if not MONGO_URL:
    logger.error(
        "MONGO mühit dəyişəni tapılmadı! .env faylına MONGO=... əlavə edin. "
        "Mongo olmadan statistika/reytinq/broadcast işləməyəcək."
    )
else:
    try:
        _client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=5000)
        _client.admin.command("ping")
        db = _client["uno_bot_db"]
        logger.info("MongoDB bağlantısı uğurlu.")
    except Exception as e:
        logger.error(f"MongoDB bağlantı xətası: {e}. Statistika/reytinq/broadcast işləməyəcək.")
        db = None
