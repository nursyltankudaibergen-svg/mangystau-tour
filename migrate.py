# -*- coding: utf-8 -*-
"""
Дерекқорды модельмен сәйкестендіретін скрипт.

Мәселе: модельге жаңа өріс қосылған (мысалы Booking.email), ал база
ескі күйінде тұр. Сондықтан "no such column: booking.email" шығады.

Бұл скрипт:
  1. Базаның КӨШІРМЕСІН жасайды (қауіпсіздік үшін)
  2. Жоқ кестелерді жасайды
  3. Жоқ бағаналарды ALTER TABLE арқылы қосады

Деректер өшпейді.

Іске қосу (жоба түбірінде):

    python migrate.py
"""

import os
import shutil
from datetime import datetime

from sqlalchemy import inspect, text

import app as app_package
from app import db
from app import models          # модельдер тіркелуі үшін керек

# -----------------------------------------------------------------------
# МАҢЫЗДЫ: create_app() ішінде seed_database() шақырылады да, ол базадан
# турларды сұрайды. Ал біз әлі жаңа бағаналарды қоспадық — сондықтан
# "no such column: tour.code" қатесі шығады.
#
# Сондықтан миграция кезінде тұқымдауды уақытша өшіреміз.
# -----------------------------------------------------------------------

if hasattr(app_package, "seed_database"):
    app_package.seed_database = lambda *args, **kwargs: None

try:
    from app import seed as seed_module
    seed_module.seed_database = lambda *args, **kwargs: None
except Exception:
    pass

app = app_package.create_app()


def backup_database():
    """instance/ ішіндегі .db файлдарының көшірмесін жасайды."""
    folder = app.instance_path

    if not os.path.isdir(folder):
        return

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")

    for name in os.listdir(folder):
        if name.endswith(".db"):
            source = os.path.join(folder, name)
            target = os.path.join(folder, "{}.{}.backup".format(name, stamp))
            shutil.copy2(source, target)
            print("Көшірме жасалды: {}".format(os.path.basename(target)))


def column_sql(column):
    """Бағананың SQL түрін құрайды."""
    try:
        type_sql = column.type.compile(db.engine.dialect)
    except Exception:
        type_sql = "TEXT"

    parts = ['"{}"'.format(column.name), type_sql]

    # SQLite бос емес бағанаға әдепкі мән талап етеді
    default = getattr(column, "default", None)

    if default is not None and getattr(default, "is_scalar", False):
        value = default.arg
        if isinstance(value, str):
            parts.append("DEFAULT '{}'".format(value.replace("'", "''")))
        elif isinstance(value, bool):
            parts.append("DEFAULT {}".format(1 if value else 0))
        elif isinstance(value, (int, float)):
            parts.append("DEFAULT {}".format(value))

    return " ".join(parts)


with app.app_context():

    backup_database()

    # 1) Жоқ кестелерді жасаймыз
    db.create_all()

    inspector = inspect(db.engine)

    added = 0

    # 2) Әр кестенің бағаналарын салыстырамыз
    for table_name, table in db.metadata.tables.items():

        if not inspector.has_table(table_name):
            print("Кесте жасалды: {}".format(table_name))
            continue

        existing = {c["name"] for c in inspector.get_columns(table_name)}

        for column in table.columns:

            if column.name in existing:
                continue

            statement = 'ALTER TABLE "{}" ADD COLUMN {}'.format(
                table_name, column_sql(column)
            )

            try:
                db.session.execute(text(statement))
                db.session.commit()
                print("Бағана қосылды: {}.{}".format(table_name, column.name))
                added += 1
            except Exception as error:
                db.session.rollback()
                print("ҚАТЕ ({}.{}): {}".format(table_name, column.name, error))

    if added:
        print("\nБарлығы {} бағана қосылды. Серверді қайта қосыңыз.".format(added))
    else:
        print("\nБаза модельмен сәйкес — өзгеріс қажет емес.")