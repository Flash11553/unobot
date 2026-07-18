#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# /broadcast üçün qrup və şəxsi istifadəçi siyahısı. Domino botundakı EYNİ
# məntiq: bir dəfə yazılan qeyd HEÇ VAXT silinmir (bot restart olsa belə).

import logging

from database import db

logger = logging.getLogger(__name__)

chats_collection = db["chats"] if db is not None else None
bc_users_collection = db["broadcast_users"] if db is not None else None


def add_served_chat(chat_id):
    if chats_collection is None:
        return
    try:
        chats_collection.update_one(
            {"_id": chat_id}, {"$setOnInsert": {"_id": chat_id}}, upsert=True
        )
    except Exception as e:
        logger.error(f"Qrup yaddaşa yazılarkən xəta: {e}")


def get_served_chats() -> list:
    if chats_collection is None:
        return []
    return list(chats_collection.find({}))


def add_served_user(user_id):
    if bc_users_collection is None:
        return
    try:
        bc_users_collection.update_one(
            {"_id": user_id}, {"$setOnInsert": {"_id": user_id}}, upsert=True
        )
    except Exception as e:
        logger.error(f"İstifadəçi yaddaşa yazılarkən xəta: {e}")


def get_served_users() -> list:
    if bc_users_collection is None:
        return []
    return list(bc_users_collection.find({}))


def _log_broadcast_error(kind, entity_id, error_message):
    filename = "errors_chats.txt" if kind == "chat" else "errors_users.txt"
    with open(filename, "a", encoding="utf-8") as file:
        file.write(f"🆔ID: {entity_id}, ❌Xəta: {error_message}\n")
