#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Səviyyə (level) və rütbə sistemi.
# Hər oyunçu ilk dəfə "1-ci yer" qazandığında (yəni oyunu qazandığında) xalı
# artır. Xallar (qələbə sayı) üst-üstə toplandıqca səviyyə və rütbə adı
# avtomatik yüksəlir. Hamı 1-ci səviyyə və ilk addan başlayır.

# (lazımi_qələbə_sayı, səviyyə, rütbə_adı)
LEVELS = [
    (0,   1,  "🔰 Yeni Başlayan"),
    (5,   2,  "🥉 Çaylaq"),
    (15,  3,  "🥈 Bacarıqlı"),
    (30,  4,  "🥇 Təcrübəli"),
    (50,  5,  "💪 Usta"),
    (80,  6,  "🔥 Ekspert"),
    (120, 7,  "👑 Master"),
    (180, 8,  "🌟 Qrandmaster"),
    (250, 9,  "🏆 Əfsanə"),
    (350, 10, "💎 Uno Kralı"),
]


def compute_level(wins: int):
    """Qələbə sayına (first_places) görə (səviyyə, rütbə_adı) qaytarır."""
    wins = wins or 0
    level, rank_name = LEVELS[0][1], LEVELS[0][2]
    for threshold, lvl, name in LEVELS:
        if wins >= threshold:
            level, rank_name = lvl, name
        else:
            break
    return level, rank_name


def place_label(place: int) -> str:
    """Yer nömrəsini emoji ilə göstərir (1-ci, 2-ci, 3-cü, 4-cü...)."""
    if place == 1:
        return "🥇 1-ci"
    if place == 2:
        return "🥈 2-ci"
    if place == 3:
        return "🥉 3-cü"
    # 4-cü, 5-ci və s. üçün sadə say + "-cü/-cı" formatı
    suffix = "-cü"
    if str(place)[-1] in ("1",):
        suffix = "-ci"
    elif str(place)[-1] in ("5", "9"):
        suffix = "-cu"
    elif str(place)[-1] in ("2", "7"):
        suffix = "-ci"
    return f"{place}{suffix}"
