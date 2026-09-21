from . import db
from .models import SiteSetting, Tour


def seed_database():
    # ============================================================
    # SITE SETTINGS
    # ============================================================

    settings = {
        "brand_name": "MANGYSTAU",
        "brand_subtitle": "TOUR",
        "phone": "+7 700 000 00 00",

        "hero_title": "DISCOVER\nMANGYSTAU",
        "hero_text": (
            "Explore the wild landscapes of Mangystau with "
            "experienced local guides and comfortable 4x4 jeeps."
        ),

        "hero_image": (
            "https://images.unsplash.com/"
            "photo-1500530855697-b586d89ba3ee?"
            "auto=format&fit=crop&w=2200&q=85"
        ),

        "logo": "",
        "whatsapp": "",
        "instagram": "",
    }

    for key, value in settings.items():
        existing = SiteSetting.query.filter_by(key=key).first()

        if not existing:
            db.session.add(
                SiteSetting(
                    key=key,
                    value=value
                )
            )

    # ============================================================
    # SIX MAIN TOURS
    # ============================================================

    tours = [
        {
            "title": "ONE DAY JOURNEY",
            "duration": "1 DAY",
            "price": "FROM $295",
            "description": (
                "Discover the highlights of Mangystau in one unforgettable day."
            ),
            "image": (
                "https://images.unsplash.com/"
                "photo-1500534623283-312aade485b7?"
                "auto=format&fit=crop&w=1200&q=85"
            ),
            "badge": "1 DAY",
            "sort_order": 1,
            "active": True,
            "code": "day1",
            "price_basic": 295000,
            "price_plus": 375000,
            "price_deluxe": 500000,
        },

        {
            "title": "TWO DAY ULTIMATE",
            "duration": "2 DAYS",
            "price": "FROM $590",
            "description": (
                "Experience the most iconic landscapes of western Mangystau "
                "with an overnight stay in Airakty."
            ),
            "image": (
                "https://images.unsplash.com/"
                "photo-1470071459604-3b5ec3a7fe05?"
                "auto=format&fit=crop&w=1200&q=85"
            ),
            "badge": "2 DAYS",
            "sort_order": 2,
            "active": True,
            "code": "day2",
            "price_basic": 295000,
            "price_plus": 375000,
            "price_deluxe": 500000,
        },

        {
            "title": "THREE DAY EXPEDITION",
            "duration": "3 DAYS",
            "price": "FROM $870",
            "description": (
                "A deeper journey through Airakty, Bozzhyra, Bokty "
                "and the spectacular landscapes of Mangystau."
            ),
            "image": (
                "https://images.unsplash.com/"
                "photo-1500534314209-a25ddb2bd429?"
                "auto=format&fit=crop&w=1200&q=85"
            ),
            "badge": "3 DAYS",
            "sort_order": 3,
            "active": True,
            "code": "day3",
            "price_basic": 435000,
            "price_plus": 555000,
            "price_deluxe": 760000,
        },

        {
            "title": "FOUR DAY MANGYSTAU",
            "duration": "4 DAYS",
            "price": "FROM $1,170",
            "description": (
                "Travel deeper into Mangystau through Tuzbair, "
                "Karaman-Ata, Bozzhyra and Kyzylkup."
            ),
            "image": (
                "https://images.unsplash.com/"
                "photo-1464822759023-fed622ff2c3b?"
                "auto=format&fit=crop&w=1200&q=85"
            ),
            "badge": "4 DAYS",
            "sort_order": 4,
            "active": True,
            "code": "day4",
            "price_basic": 585000,
            "price_plus": 745000,
            "price_deluxe": 1030000,
        },

        {
            "title": "FIVE DAY VACATION",
            "duration": "5 DAYS",
            "price": "FROM $1,590",
            "description": (
                "Five days of spectacular landscapes, "
                "remote locations and unforgettable desert adventures."
            ),
            "image": (
                "https://images.unsplash.com/"
                "photo-1501785888041-af3ef285b470?"
                "auto=format&fit=crop&w=1200&q=85"
            ),
            "badge": "5 DAYS",
            "sort_order": 5,
            "active": True,
            "code": "day5",
            "price_basic": 795000,
            "price_plus": 995000,
            "price_deluxe": 1360000,
        },

        {
            "title": "SIX DAY GRAND TOUR",
            "duration": "6 DAYS",
            "price": "FROM $2,166",
            "description": (
                "The complete Mangystau adventure covering "
                "the region's most remarkable landscapes."
            ),
            "image": (
                "https://images.unsplash.com/"
                "photo-1500530855697-b586d89ba3ee?"
                "auto=format&fit=crop&w=1200&q=85"
            ),
            "badge": "6 DAYS",
            "sort_order": 6,
            "active": True,
            "code": "day6",
            "price_basic": 1083000,
            "price_plus": 1323000,
            "price_deluxe": 1768000,
        },
    ]

    # ============================================================
    # ADD / UPDATE TOURS
    # ============================================================

    for item in tours:
        tour = Tour.query.filter_by(code=item["code"]).first()

        if tour:
            tour.title = item["title"]
            tour.duration = item["duration"]
            tour.price = item["price"]
            tour.description = item["description"]
            tour.image = item["image"]
            tour.badge = item["badge"]
            tour.sort_order = item["sort_order"]
            tour.active = item["active"]

            tour.price_basic = item["price_basic"]
            tour.price_plus = item["price_plus"]
            tour.price_deluxe = item["price_deluxe"]

        else:
            db.session.add(
                Tour(
                    title=item["title"],
                    duration=item["duration"],
                    price=item["price"],
                    description=item["description"],
                    image=item["image"],
                    badge=item["badge"],
                    sort_order=item["sort_order"],
                    active=item["active"],
                    code=item["code"],
                    price_basic=item["price_basic"],
                    price_plus=item["price_plus"],
                    price_deluxe=item["price_deluxe"],
                )
            )

    # ============================================================
    # REMOVE OLD TOURS
    # ============================================================

    valid_codes = {
        "day1",
        "day2",
        "day3",
        "day4",
        "day5",
        "day6",
    }

    old_tours = Tour.query.all()

    for tour in old_tours:
        if tour.code not in valid_codes:
            db.session.delete(tour)

    # ============================================================
    # SAVE
    # ============================================================

    db.session.commit()