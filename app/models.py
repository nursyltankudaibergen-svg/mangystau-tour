from datetime import datetime

from . import db


class SiteSetting(db.Model):
    id = db.Column(
        db.Integer,
        primary_key=True
    )

    key = db.Column(
        db.String(80),
        unique=True,
        nullable=False
    )

    value = db.Column(
        db.Text,
        nullable=False,
        default=""
    )


class Tour(db.Model):
    id = db.Column(
        db.Integer,
        primary_key=True
    )

    title = db.Column(
        db.String(160),
        nullable=False
    )

    duration = db.Column(
        db.String(80),
        default=""
    )

    # Price is stored as text
    # Example: 165 000 or $165 000
    price = db.Column(
        db.String(100),
        default=""
    )

    description = db.Column(
        db.Text,
        default=""
    )

    image = db.Column(
        db.String(500),
        default=""
    )

    badge = db.Column(
        db.String(40),
        default=""
    )

    sort_order = db.Column(
        db.Integer,
        default=0
    )

    active = db.Column(
        db.Boolean,
        default=True
    )

    # ЖАҢА: маршруттарды турға байлайтын тұрақты кілт.
    # Тур атауын өзгертсең де маршруттар жоғалмайды.
    # Мысалы: day1, day2, day3...
    code = db.Column(
        db.String(40),
        default=""
    )

    # ЖАҢА: пакет бағалары (₸). 0 болса — routes.py ішіндегі
    # PACKAGE_PRICES кестесі алынады. Админкадан өзгертіледі.
    price_basic = db.Column(
        db.Integer,
        default=0
    )

    price_plus = db.Column(
        db.Integer,
        default=0
    )

    price_deluxe = db.Column(
        db.Integer,
        default=0
    )


class TourRoute(db.Model):
    id = db.Column(
        db.Integer,
        primary_key=True
    )

    tour_id = db.Column(
        db.Integer,
        db.ForeignKey("tour.id"),
        nullable=False
    )

    day_number = db.Column(
        db.Integer,
        default=1
    )

    title = db.Column(
        db.String(300),
        nullable=False
    )

    description = db.Column(
        db.Text,
        default=""
    )

    price = db.Column(
        db.String(100),
        default=""
    )

    duration = db.Column(
        db.String(100),
        default=""
    )

    vehicle = db.Column(
        db.String(100),
        default="4x4 Jeep"
    )

    group_size = db.Column(
        db.String(100),
        default="1-4 Guests"
    )

    sort_order = db.Column(
        db.Integer,
        default=0
    )

    active = db.Column(
        db.Boolean,
        default=True
    )

    # ЖАҢА ӨРІСТЕР
    # -----------------------------------------------------------------
    # image — маршруттың суреті. Админкадан жүктелген файлдың жолы,
    #         мысалы "routes/day2-01.jpg". Бос болса, код static/routes/
    #         ішінен келісілген атаумен өзі іздейді.
    image = db.Column(
        db.String(500),
        default=""
    )

    # note — қысқа ескерту. Мысалы: "Жаңбырда Тұзбайырға түспейміз"
    note = db.Column(
        db.String(300),
        default=""
    )

    # km — маршруттың шақырымы. 0 болса, сайтта көрсетілмейді.
    km = db.Column(
        db.Integer,
        default=0
    )

    tour = db.relationship(
        "Tour",
        backref=db.backref(
            "routes",
            lazy=True,
            cascade="all, delete-orphan"
        )
    )


class Booking(db.Model):
    id = db.Column(
        db.Integer,
        primary_key=True
    )

    name = db.Column(
        db.String(120),
        nullable=False
    )

    email = db.Column(
        db.String(160),
        default=""
    )

    phone = db.Column(
        db.String(50),
        nullable=False
    )

    tour = db.Column(
        db.String(160),
        default=""
    )

    guests = db.Column(
        db.Integer,
        default=1
    )

    tour_date = db.Column(
        db.Date,
        nullable=True
    )

    message = db.Column(
        db.Text,
        default=""
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )

    status = db.Column(
        db.String(30),
        default="Новая"
    )

    # ЖАҢА ӨРІСТЕР
    # -----------------------------------------------------------------
    # Бұрын бәрі message ішіне мәтін болып жазылатын. Енді бөлек
    # бағаналарда — сондықтан админкада кестемен сүзуге, сұрыптауға
    # және жалпы соманы санауға болады.

    # basic / plus / deluxe
    package = db.Column(
        db.String(30),
        default=""
    )

    # Бір күндік турда таңдалған бағыт
    route = db.Column(
        db.String(300),
        default=""
    )

    # Топ (көлік) саны
    groups = db.Column(
        db.Integer,
        default=1
    )

    # Қосымша қызметтер: "drone,shower,starlink"
    services = db.Column(
        db.String(300),
        default=""
    )

    # Жалпы сома, теңгемен
    total_price = db.Column(
        db.Integer,
        default=0
    )

    # Менеджердің өз жазбасы (клиентке көрінбейді)
    admin_note = db.Column(
        db.Text,
        default=""
    )


class Review(db.Model):
    id = db.Column(
        db.Integer,
        primary_key=True
    )

    name = db.Column(
        db.String(120),
        nullable=False
    )

    rating = db.Column(
        db.Integer,
        default=5
    )

    text = db.Column(
        db.Text,
        default=""
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )

    active = db.Column(
        db.Boolean,
        default=True
    )

    # ЖАҢА ӨРІСТЕР
    # -----------------------------------------------------------------
    # Бұл екеуі routes.py ішінде БҰРЫННАН қолданылып жүрген, бірақ
    # модельде болмағандықтан пікір қосқанда қате шығатын.

    # Қонақтың елі: "Kazakhstan", "United Kingdom"
    country = db.Column(
        db.String(120),
        default=""
    )

    # Суреттің жолы немесе сілтемесі
    photo = db.Column(
        db.String(500),
        default=""
    )

    # Қай турға қатысты пікір (міндетті емес)
    tour = db.Column(
        db.String(160),
        default=""
    )