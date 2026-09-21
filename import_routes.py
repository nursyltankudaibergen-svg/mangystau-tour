# -*- coding: utf-8 -*-
"""
Кодтағы дайын маршруттарды ДЕРЕКҚОРҒА көшіреді.

Не үшін: содан кейін маршруттарды админкадан өңдей аласың — мәтінін
өзгерту, сурет жүктеу, әр бағытқа өз бағасын қою.

Іске қосу (жоба түбірінде):

    python import_routes.py            # орысша мәтінмен
    python import_routes.py en         # ағылшынша мәтінмен

МАҢЫЗДЫ:
  * Маршруты БАР турлар аттап өтіледі — қолмен жазғаның жоғалмайды.
  * Скриптті қайта іске қосуға болады, қайталап қоспайды.
  * Аударма жоғалады: базада бір ғана тілдегі мәтін сақталады.
    Сайт сол мәтінді барлық тілде көрсетеді.
"""

import sys

from app import create_app, db
from app.models import Tour, TourRoute
from app.routes import ROUTE_FALLBACK, duration_days, localize, price_number


LANGUAGE = (sys.argv[1] if len(sys.argv) > 1 else "ru").strip().lower()


app = create_app()


with app.app_context():

    tours = Tour.query.order_by(Tour.sort_order, Tour.id).all()

    added = 0
    skipped = 0

    for tour in tours:

        days = duration_days(tour.duration or "")
        key = "day{}".format(days)

        items = ROUTE_FALLBACK.get(key, [])

        if not items:
            print("~ {}: дайын маршрут жоқ ({})".format(tour.title, tour.duration))
            continue

        existing = TourRoute.query.filter_by(tour_id=tour.id).count()

        if existing:
            print("= {}: базада {} маршрут бар, аттап өтемін".format(tour.title, existing))
            skipped += 1
            continue

        # --- Tour.code: маршруттарды турға байлайтын тұрақты кілт ---
        if hasattr(tour, "code") and not (tour.code or "").strip():
            tour.code = key

        for index, item in enumerate(items, start=1):

            route = TourRoute(
                tour_id=tour.id,
                day_number=index,
                sort_order=index,
                title=localize(item.get("title"), LANGUAGE) or "",
                description=localize(item.get("desc"), LANGUAGE) or "",
                active=True,
            )

            # Ескерту өрісі модельде бар болса ғана
            if hasattr(route, "note"):
                route.note = localize(item.get("note"), LANGUAGE) or ""

            if hasattr(route, "km"):
                route.km = int(item.get("km") or 0)

            # Сурет: static/routes/day2-01.jpg үлгісімен
            if hasattr(route, "image"):
                route.image = "routes/day{}-{:02d}.jpg".format(days, index)

            # Баға: бір күндік турда әр бағытқа бөлек баға керек,
            # сондықтан бастапқы мән ретінде турдың бағасын қоямыз.
            if days == 1:
                route.price = str(price_number(tour.price) or "")

            db.session.add(route)
            added += 1

            print("+ {} · {:02d} · {}".format(
                tour.title, index, (route.title or "")[:60]
            ))

    db.session.commit()

    print("\nҚосылды: {} маршрут".format(added))

    if skipped:
        print("Аттап өтілді: {} тур (базада маршруты бар)".format(skipped))

    if added:
        print("\nЕнді админкадағы «Маршруттар» бөлімінен өңдей аласың.")
        print("Ескерту: суреттің жолы static/routes/dayN-01.jpg деп қойылды —")
        print("файл жоқ болса, админкадан жүктеуге болады.")