# -*- coding: utf-8 -*-
"""
Админкадағы бүлінген жолдарды тазалайтын бір реттік скрипт.

Терминалда жобаның түбірінде тұрып:

    python tazalau.py

Ол logo / hero_video / hero_image / hero_poster өрістерін тексереді.
Бүлінген мән тапса (мысалы "https:98751290-5a8f-..." сияқты жартыкеш
сілтеме), сол өрісті БОСАТАДЫ — сонда сайт әдепкі файлды алады.
"""

from app import create_app, db
from app.models import SiteSetting

MEDIA_KEYS = ["logo", "hero_video", "hero_image", "hero_poster"]


def is_broken(value):
    value = (value or "").strip()

    if not value:
        return False

    # "https:xxx" — қос сызықсыз жартыкеш сілтеме
    if value.startswith(("http:", "https:")) and not value.startswith(("http://", "https://")):
        return True

    return False


app = create_app()

with app.app_context():

    changed = 0

    for row in SiteSetting.query.all():

        if row.key in MEDIA_KEYS and is_broken(row.value):
            print("Тазаланды: {} = {!r}".format(row.key, row.value))
            row.value = ""
            changed += 1

    if changed:
        db.session.commit()
        print("\nБарлығы {} өріс тазаланды.".format(changed))
    else:
        print("Бүлінген мән табылмады.")