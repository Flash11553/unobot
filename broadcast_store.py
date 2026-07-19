#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# /broadcast üçün qrup və şəxsi istifadəçi siyahısı. Domino botundakı EYNİ
# məntiq: bir dəfə yazılan qeyd HEÇ VAXT silinmir (bot restart olsa belə).
#
# QEYD (GERİYƏ UYĞUNLUQ): Bu kolleksiyalarda tarix boyu İKİ fərqli sxem
# istifadə olunub - köhnə sənədlərdə identifikator "_id" sahəsindədir, yeni
# sənədlərdə isə açıq "chat_id"/"user_id" sahəsindədir. get_served_chats()/
# get_served_users() HƏR İKİ formatı normallaşdıraraq HƏMİŞƏ "chat_id"/
# "user_id" açarı ilə qaytarır ki, çağıran kod (broadcast.py) sxem
# fərqindən asılı olmadan işləsin - əks halda köhnə formatlı bir sənəd
# bütün broadcast dövrəsini səssizcə yarımçıq kəsə bilərdi.

import logging

from database import db

logger = logging.getLogger(__name__)

chats_collection = db["chats"] if db is not None else None
bc_users_collection = db["broadcast_users"] if db is not None else None


def add_served_chat(chat_id):
    if chats_collection is None:
        return
    try:
        # Əvvəlcə köhnə formatda (yalnız _id) qeyd olub-olmadığını yoxla ki,
        # təkrar (dublikat) sənəd yaranmasın
        existing = chats_collection.find_one(
            {"$or": [{"chat_id": chat_id}, {"_id": chat_id}]}
        )
        if existing:
            return
        chats_collection.update_one(
            {"chat_id": chat_id},
            {"$setOnInsert": {"chat_id": chat_id}},
            upsert=True,
        )
    except Exception as e:
        logger.error(f"Qrup yaddaşa yazılarkən xəta: {e}")


def get_served_chats() -> list:
    """Hər sənədi HƏMİŞƏ {'chat_id': <id>} formatında qaytarır - köhnə
    formatlı sənədlər (yalnız _id) də daxil olmaqla. Eyni ID üçün BİRDƏN
    ARTIQ sənəd olsa belə (əvvəlki sxem versiyalarından qalma), nəticədə
    hər ID YALNIZ BİR DƏFƏ görünür."""
    if chats_collection is None:
        return []
    seen = set()
    result = []
    try:
        for doc in chats_collection.find({}):
            chat_id = doc.get("chat_id")
            if chat_id is None:
                chat_id = doc.get("_id")
            if chat_id is not None and chat_id not in seen:
                seen.add(chat_id)
                result.append({"chat_id": chat_id})
    except Exception as e:
        logger.error(f"Qruplar oxunarkən xəta: {e}")
    return result


def add_served_user(user_id):
    if bc_users_collection is None:
        return
    try:
        existing = bc_users_collection.find_one(
            {"$or": [{"user_id": user_id}, {"_id": user_id}]}
        )
        if existing:
            return
        bc_users_collection.update_one(
            {"user_id": user_id},
            {"$setOnInsert": {"user_id": user_id}},
            upsert=True,
        )
    except Exception as e:
        logger.error(f"İstifadəçi yaddaşa yazılarkən xəta: {e}")


def get_served_users() -> list:
    """Hər sənədi HƏMİŞƏ {'user_id': <id>} formatında qaytarır - köhnə
    formatlı sənədlər (yalnız _id) də daxil olmaqla. Eyni ID üçün BİRDƏN
    ARTIQ sənəd olsa belə (əvvəlki sxem versiyalarından qalma), nəticədə
    hər ID YALNIZ BİR DƏFƏ görünür - bu, eyni istifadəçiyə reklamın 2-3
    dəfə getməsinin qarşısını alır."""
    if bc_users_collection is None:
        return []
    seen = set()
    result = []
    try:
        for doc in bc_users_collection.find({}):
            user_id = doc.get("user_id")
            if user_id is None:
                user_id = doc.get("_id")
            if user_id is not None and user_id not in seen:
                seen.add(user_id)
                result.append({"user_id": user_id})
    except Exception as e:
        logger.error(f"İstifadəçilər oxunarkən xəta: {e}")
    return result


def _log_broadcast_error(kind, entity_id, error_message):
    filename = "errors_chats.txt" if kind == "chat" else "errors_users.txt"
    with open(filename, "a", encoding="utf-8") as file:
        file.write(f"🆔ID: {entity_id}, ❌Xəta: {error_message}\n")
