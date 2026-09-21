# -*- coding: utf-8 -*-
"""
КОМПЬЮТЕРДЕГІ ДЕРЕКТЕРДІ NEON-ҒА КӨШІРУ

Не істейді: instance/mangystau.sqlite3 ішіндегі бәрін — турлар, маршруттар,
бағалар, баптаулар, пікірлер, өтінімдер — Neon базасына көшіреді.

Іске қосу (жоба түбірінде, .env ішінде DATABASE_URL тұрғанда):

    python copy_to_neon.py              # Neon бос болса ғана көшіреді
    python copy_to_neon.py --replace    # Neon-дағыны өшіріп, қайта көшіреді

МАҢЫЗДЫ: сайтты DATABASE_URL-мен бірінші рет іске қоспас бұрын жүргіз.
Әйтпесе сайт Neon-ға бастапқы үлгі турларды жазып қояды — онда
--replace белгісімен іске қосасың.
"""

import os
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect, select, text


ROOT = Path(__file__).resolve().parent
SQLITE_PATH = ROOT / "instance" / "mangystau.sqlite3"

REPLACE = "--replace" in sys.argv

# Кестелердің реті маңызды: tour_route турға сілтейді,
# сондықтан турлар бірінші көшіріледі.
TABLE_ORDER = ["site_setting", "tour", "tour_route", "review", "booking"]


# ---------------------------------------------------------------------------
# .env оқу
# ---------------------------------------------------------------------------

def read_env():
    path = ROOT / ".env"
    if not path.is_file():
        return

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


read_env()

target_url = (os.getenv("DATABASE_URL") or "").strip()

if target_url.startswith("postgres://"):
    target_url = "postgresql://" + target_url[len("postgres://"):]

if not target_url.startswith("postgresql"):
    sys.exit("ҚАТЕ: .env ішінде DATABASE_URL жоқ немесе ол Postgres мекенжайы емес.")

# Драйвер: psycopg2 немесе psycopg (3-нұсқа) — қайсысы орнатылса
try:
    import psycopg2  # noqa: F401
except ImportError:
    try:
        import psycopg  # noqa: F401
        target_url = "postgresql+psycopg://" + target_url.split("://", 1)[1]
    except ImportError:
        sys.exit(
            "ҚАТЕ: Postgres драйвері орнатылмаған. Терминалда:\n"
            "    pip install \"psycopg[binary]\"\n"
            "сосын қайта іске қос."
        )

if not SQLITE_PATH.is_file():
    sys.exit("ҚАТЕ: {} табылмады.".format(SQLITE_PATH))


# ---------------------------------------------------------------------------
# Модельдерді жүктейміз — create_app() шақырмаймыз,
# әйтпесе сайт Neon-ға үлгі турларды жазып жібереді.
# ---------------------------------------------------------------------------

sys.path.insert(0, str(ROOT))

from app import db          # noqa: E402
from app import models      # noqa: E402,F401  — кестелер тіркелсін

metadata = db.metadata

source = create_engine("sqlite:///" + str(SQLITE_PATH))
target = create_engine(target_url, pool_pre_ping=True)

print("Көзі:     ", SQLITE_PATH.name)
print("Мақсаты:  ", target.url.host, "/", target.url.database)
print()


# ---------------------------------------------------------------------------
# 1. Neon-да кестелерді жасаймыз (толық, барлық жаңа бағандармен)
# ---------------------------------------------------------------------------

metadata.create_all(target)

source_inspector = inspect(source)
source_tables = set(source_inspector.get_table_names())


# ---------------------------------------------------------------------------
# 2. Neon бос па?
# ---------------------------------------------------------------------------

with target.connect() as conn:
    existing = {
        name: conn.execute(text('SELECT COUNT(*) FROM "{}"'.format(name))).scalar()
        for name in TABLE_ORDER
        if name in metadata.tables
    }

if any(existing.values()) and not REPLACE:
    print("Neon-да деректер бар:")
    for name, count in existing.items():
        if count:
            print("   {:14} {} жол".format(name, count))
    print()
    print("Үстінен жазу үшін:  python copy_to_neon.py --replace")
    sys.exit(1)


# ---------------------------------------------------------------------------
# 3. Көшіру
# ---------------------------------------------------------------------------

total = 0

with target.begin() as dest:

    if REPLACE:
        # Кері ретпен тазалаймыз — сілтемелер бұзылмасын
        for name in reversed(TABLE_ORDER):
            if name in metadata.tables:
                dest.execute(text('DELETE FROM "{}"'.format(name)))
        print("Neon тазаланды.\n")

    for name in TABLE_ORDER:

        if name not in metadata.tables:
            continue

        table = metadata.tables[name]

        if name not in source_tables:
            print("~ {:14} компьютерде жоқ, өткізіп жіберемін".format(name))
            continue

        # Тек екі жақта да бар бағандарды аламыз
        source_columns = {c["name"] for c in source_inspector.get_columns(name)}
        columns = [c for c in table.columns if c.name in source_columns]

        with source.connect() as src:
            rows = src.execute(select(*columns)).mappings().all()

        clean_rows = []

        for row in rows:
            item = dict(row)

            # Postgres жол ұзындығын қатаң тексереді, SQLite — жоқ.
            # Тым ұзын мәтінді қысқартамыз, әйтпесе көшіру тоқтап қалады.
            for column in columns:
                length = getattr(column.type, "length", None)
                value = item.get(column.name)
                if length and isinstance(value, str) and len(value) > length:
                    item[column.name] = value[:length]

            clean_rows.append(item)

        if clean_rows:
            dest.execute(table.insert(), clean_rows)

        total += len(clean_rows)
        print("+ {:14} {} жол".format(name, len(clean_rows)))

    # -----------------------------------------------------------------------
    # 4. Postgres санауышын түзейміз — әйтпесе жаңа тур/өтінім қосқанда
    #    "duplicate key" қатесі шығады (id 1-ден қайта басталады)
    # -----------------------------------------------------------------------

    for name in TABLE_ORDER:
        if name in metadata.tables and "id" in metadata.tables[name].columns:
            dest.execute(text(
                "SELECT setval(pg_get_serial_sequence('\"{0}\"', 'id'), "
                "COALESCE((SELECT MAX(id) FROM \"{0}\"), 0) + 1, false)".format(name)
            ))

print()
print("Дайын: барлығы {} жол көшірілді.".format(total))
print("Енді сайтты іске қос:  python run.py")