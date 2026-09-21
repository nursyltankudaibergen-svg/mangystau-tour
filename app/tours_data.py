# -*- coding: utf-8 -*-
"""
Маршруттар мен пакеттердің ДЕРЕКТЕРІ.

Бұрын маршруттар tour_detail.html ішінде тур АТАУЫНА байланып тұрған:
    {% if tour.title == "FOUR DAY MANGYSTAU" %}
Админкада атауды сәл өзгертсең — маршрут үнсіз жоғалатын.

Енді бәрі осы файлда, кілт ретінде тұрақты `code` қолданылады
("day1" ... "day6"). Тур атауын қалағаныңша өзгерте бер.
"""

import re

# ---------------------------------------------------------------------------
# ПАКЕТТЕР: BASIC / PLUS / DELUXE
# ---------------------------------------------------------------------------
# multiplier — базалық тур бағасына көбейткіш.
#   BASIC  = 1.00  (тур бағасы сол күйінде)
#   PLUS   = 1.25  (+25%)
#   DELUXE = 1.60  (+60%)
#
# Пайызбен істегеніміз әдейі: 1 күндік турға да, 6 күндікке де
# фото/дрон қызметінің құны әртүрлі болады.

PACKAGES = [
    {
        "code": "basic",
        "name": "BASIC",
        "multiplier": 1.00,
        "popular": False,
        "tagline": {
            "en": "The route itself, done properly.",
            "kz": "Маршруттың өзі — сапалы деңгейде.",
            "ru": "Сам маршрут, без лишнего.",
            "zh": "纯粹的路线体验。",
        },
        "features": [
            {"en": "Private 4×4 with a guide-driver",
             "kz": "Жүргізуші-гидпен жеке 4×4 көлік",
             "ru": "Личный 4×4 с водителем-гидом",
             "zh": "配司机兼向导的私人四驱车"},
            {"en": "Meals, water and camp equipment",
             "kz": "Тамақ, су және лагерь жабдығы",
             "ru": "Питание, вода и снаряжение для лагеря",
             "zh": "餐食、饮水与露营装备"},
            {"en": "All park fees and permits",
             "kz": "Барлық рұқсат пен кіру ақысы",
             "ru": "Все разрешения и входные сборы",
             "zh": "所有许可与门票费用"},
            {"en": "Phone photos from your guide",
             "kz": "Гид түсірген телефон суреттері",
             "ru": "Фото с телефона от гида",
             "zh": "向导用手机拍摄的照片"},
        ],
    },
    {
        "code": "plus",
        "name": "PLUS",
        "multiplier": 1.25,
        "popular": True,
        "tagline": {
            "en": "Everything in Basic, plus real photos of your trip.",
            "kz": "Basic-тегінің бәрі, үстіне сапарыңыздың нағыз суреттері.",
            "ru": "Всё из Basic плюс настоящие фото вашей поездки.",
            "zh": "包含 Basic 全部内容，另加专业旅拍。",
        },
        "features": [
            {"en": "Everything in Basic",
             "kz": "Basic-тегінің бәрі",
             "ru": "Всё, что входит в Basic",
             "zh": "包含 Basic 的全部内容"},
            {"en": "Photo session at the main viewpoints",
             "kz": "Негізгі көрініс нүктелерінде фотосессия",
             "ru": "Фотосессия на главных смотровых точках",
             "zh": "在主要观景点进行拍摄"},
            {"en": "40+ edited photos within 5 days",
             "kz": "5 күн ішінде 40+ өңделген сурет",
             "ru": "40+ обработанных фото в течение 5 дней",
             "zh": "5 天内交付 40+ 张精修照片"},
            {"en": "Drone shots at two locations",
             "kz": "Екі локацияда дрон түсірілімі",
             "ru": "Съёмка с дрона на двух локациях",
             "zh": "两处地点的无人机拍摄"},
        ],
    },
    {
        "code": "deluxe",
        "name": "DELUXE",
        "multiplier": 1.60,
        "popular": False,
        "tagline": {
            "en": "A separate guide and a full film crew for your trip.",
            "kz": "Бөлек гид және сапарыңызға арналған толық түсірілім тобы.",
            "ru": "Отдельный гид и полноценная съёмочная группа.",
            "zh": "专属向导与完整摄制团队。",
        },
        "features": [
            {"en": "Everything in Plus",
             "kz": "Plus-тегінің бәрі",
             "ru": "Всё, что входит в Plus",
             "zh": "包含 Plus 的全部内容"},
            {"en": "Dedicated private guide, separate from the driver",
             "kz": "Жүргізушіден бөлек жеке гид",
             "ru": "Отдельный персональный гид, помимо водителя",
             "zh": "除司机外，另配专属私人向导"},
            {"en": "Photographer and videographer for the whole route",
             "kz": "Бүкіл маршрут бойы фотограф және видеограф",
             "ru": "Фотограф и видеограф на всём маршруте",
             "zh": "全程随行摄影师与摄像师"},
            {"en": "Edited 2–3 min drone film of your trip",
             "kz": "Сапарыңыз туралы 2–3 минуттық дрон-фильм",
             "ru": "Смонтированный 2–3 мин. фильм с дрона",
             "zh": "2–3 分钟无人机短片成片"},
            {"en": "Priority dates and airport pick-up",
             "kz": "Кезектен тыс күндер және әуежайдан қарсы алу",
             "ru": "Приоритетные даты и встреча в аэропорту",
             "zh": "优先日期安排与机场接送"},
        ],
    },
]

PACKAGE_CODES = [p["code"] for p in PACKAGES]
DEFAULT_PACKAGE = "basic"


def get_package(code):
    """Пакетті кодпен табады. Жоқ болса — BASIC."""
    for package in PACKAGES:
        if package["code"] == code:
            return package
    return PACKAGES[0]


def package_price(base_price, package_code):
    """Базалық бағаны пакетке қарай есептейді. 1000-ға дейін дөңгелектейді."""
    try:
        base = float(base_price or 0)
    except (TypeError, ValueError):
        return 0
    if base <= 0:
        return 0
    total = base * get_package(package_code)["multiplier"]
    return int(round(total / 1000.0) * 1000)


# ---------------------------------------------------------------------------
# КӨМЕКШІ ФУНКЦИЯЛАР
# ---------------------------------------------------------------------------

def localize(value, language, fallback="en"):
    """
    Мәтін не жай жол, не {"en": ..., "kz": ...} сөздігі болуы мүмкін.
    Екеуін де қабылдайды. Аудармасы жоқ болса — EN.
    """
    if isinstance(value, dict):
        return value.get(language) or value.get(fallback) or ""
    return value or ""


def duration_days(duration):
    """
    "3 күн", "2 DAYS / 1 NIGHT", "10 days" -> 3, 2, 10

    Бұрынғы код `duration|first == '1'` деп бірінші СИМВОЛҒА қарайтын,
    сондықтан "10 days" бір күндік тур болып саналатын. Енді сан толық оқылады.
    """
    match = re.search(r"\d+", str(duration or ""))
    return int(match.group()) if match else 0


def _field(tour, name, default=None):
    """Tour объекті де, dict те бола береді."""
    if isinstance(tour, dict):
        return tour.get(name, default)
    return getattr(tour, name, default)


def route_key(tour):
    """
    Турдың маршрут кілтін анықтайды.
    1) tour.code бар болса — сол (ең сенімдісі, админкадан өзгермейді)
    2) болмаса — duration ішіндегі саннан "day3" сияқты кілт құралады
    """
    code = _field(tour, "code")
    if code and code in ROUTES:
        return code
    days = duration_days(_field(tour, "duration"))
    key = "day{}".format(days)
    return key if key in ROUTES else None


def routes_for(tour):
    """Шаблон осы функцияны шақырады. Табылмаса — бос тізім."""
    key = route_key(tour)
    return ROUTES.get(key, {}).get("items", []) if key else []


def route_meta(tour):
    key = route_key(tour)
    return ROUTES.get(key, {}) if key else {}


# ---------------------------------------------------------------------------
# МАРШРУТТАР
# ---------------------------------------------------------------------------
# unit: "route" — бір күндік турдағы таңдау нұсқалары
#       "day"   — көп күндік турдағы күндер
#
# desc/title мәнін кез келген жерде {"en": ..., "ru": ...} сөздігіне
# ауыстыруға болады — localize() екеуін де түсінеді.

ROUTES = {
    "day1": {
        "label": {"en": "One day journey", "kz": "Бір күндік сапар",
                  "ru": "Однодневная поездка", "zh": "一日行程"},
        "unit": "route",
        "items": [
            {
                "n": 1,
                "title": "Ybykty-Sai • Tuzbair",
                "image": "routes/route01.jpg",
                "desc": "Explore the Ybykty-Sai canyon, then continue to the white "
                        "salt flats and limestone cliffs of Tuzbair.",
            },
            {
                "n": 2,
                "title": "Torysh • Tuzbair",
                "image": "routes/route02.jpg",
                "note": {"en": "In rainy weather the descent to Tuzbair is not possible.",
                         "kz": "Жаңбырлы ауа райында Тұзбайырға түсу мүмкін емес.",
                         "ru": "В дождливую погоду спуск к Тузбаиру невозможен.",
                         "zh": "雨天无法下到图兹拜尔。"},
                "desc": "Visit the Torysh valley of stone balls and continue to Tuzbair.",
            },
            {
                "n": 3,
                "title": "Karamsai • Shakpak-Ata • Torysh • Kokala • Sherkala • Airakty",
                "image": "routes/route03.jpg",
                "desc": "A full day through Karamsai canyon, the Shakpak-Ata underground "
                        "mosque, Torysh, Kokala, Sherkala mountain and the Airakty "
                        "Valley of Castles.",
            },
            {
                "n": 4,
                "title": "Ybykty-Sai • Kyzylkup • Bozzhyra",
                "image": "routes/route04.jpg",
                "desc": "From Ybykty-Sai canyon to the striped hills of Kyzylkup, "
                        "finishing at the cliffs of Bozzhyra.",
            },
            {
                "n": 5,
                "title": "Kyzylkup • Bokty • Bozzhyra",
                "image": "routes/route05.jpg",
                "note": {"en": "In rainy weather Mount Bokty is not visited.",
                         "kz": "Жаңбырлы ауа райында Бөкті тауына бармаймыз.",
                         "ru": "В дождливую погоду гору Бокты не посещаем.",
                         "zh": "雨天不前往博克特山。"},
                "desc": "Discover Kyzylkup, Mount Bokty and Bozzhyra in one day.",
            },
        ],
    },

    "day2": {
        "label": {"en": "Two day ultimate", "kz": "Екі күндік сапар",
                  "ru": "Двухдневный тур", "zh": "两日行程"},
        "unit": "day",
        "items": [
            {
                "n": 1,
                "title": "Aktau • Karamsai • Shakpak-Ata • Torysh • Kokala • Sherkala • Airakty",
                "note": "Overnight at the Airakty Valley of Castles",
                "image": "routes/route01.jpg",
                "desc": "Meet your guide at your hotel or at Aktau airport. First stop at "
                        "Karamsai canyon, then the underground mosque of Shakpak-Ata carved "
                        "into a chalk cliff above the Caspian coast. Continue to the Torysh "
                        "valley with its thousands of round stone concretions, a short photo "
                        "stop at Kokala, then Mount Sherkala. The day ends at the Airakty "
                        "Valley of Castles.",
            },
            {
                "n": 2,
                "title": "Bozzhyra • Bokty • Kyzylkup",
                "note": "Bozzhyra (2 viewpoints) • Bokty • Kyzylkup (Tiramisu)",
                "image": "routes/route02.jpg",
                "desc": "In the morning head to Bozzhyra for the main panoramic viewpoints "
                        "and the white cliffs. Continue to Mount Bokty, a striped pyramid "
                        "rising above the steppe, and finish at Kyzylkup with its red and "
                        "white geological layers. Return to Aktau in the evening.",
            },
        ],
    },

    "day3": {
        "label": {"en": "Three day expedition", "kz": "Үш күндік экспедиция",
                  "ru": "Трёхдневная экспедиция", "zh": "三日探索"},
        "unit": "day",
        "items": [
            {
                "n": 1,
                "title": "Aktau • Karamsai • Shakpak-Ata • Torysh • Kokala • Sherkala • Airakty",
                "note": "Airakty Valley of Castles • overnight camp",
                "image": "routes/route01.jpg",
                "desc": "Meet your guide at the hotel or airport in Aktau. Karamsai canyon, "
                        "the Shakpak-Ata underground mosque, the Torysh valley of giant stone "
                        "concretions, a stop at Kokala and Sherkala mountain. The day ends at "
                        "the Airakty Valley of Castles, where you stay overnight.",
            },
            {
                "n": 2,
                "title": "Airakty • Bozzhyra",
                "note": "Martian panorama • Dragon Ridge • lower Bozzhyra",
                "image": "routes/route02.jpg",
                "desc": "Start with a short morning hike and panoramic views over Airakty. "
                        "After breakfast head to Bozzhyra: the Martian panorama, Dragon Ridge "
                        "and the lower part of the valley. Field lunch among the cliffs and "
                        "a night at camp.",
            },
            {
                "n": 3,
                "title": "Bozzhyra panorama • Bokty • Kyzylkup • Aktau",
                "note": "Panorama • Mount Bokty • Kyzylkup • return to Aktau",
                "image": "routes/route03.jpg",
                "desc": "After breakfast continue along the Bozzhyra panorama and its "
                        "viewpoints, then Mount Bokty and the colourful layers of Kyzylkup. "
                        "After lunch, the return journey to Aktau.",
            },
        ],
    },

    "day4": {
        "label": {"en": "Four day Mangystau", "kz": "Төрт күндік Маңғыстау",
                  "ru": "Четырёхдневный Мангистау", "zh": "四日曼吉斯套"},
        "unit": "day",
        "items": [
            {
                "n": 1,
                "title": "Aktau • Karamsai • Shakpak-Ata • Torysh • Kokala • Sherkala • Airakty",
                "note": "Torysh stone balls • Sherkala • Airakty",
                "image": "routes/route01.jpg",
                "desc": "Meet your guide-driver at your hotel or Aktau airport. Karamsai canyon "
                        "and the Shakpak-Ata underground mosque, then the Torysh stone ball "
                        "valley and Kokala. After lunch, Sherkala mountain and the Airakty "
                        "Valley of Castles.",
            },
            {
                "n": 2,
                "title": "Airakty • Tuzbair • Karaman-Ata • Ybykty-Sai",
                "note": "Tuzbair salt marsh • natural arch • camp",
                "image": "routes/route02.jpg",
                "desc": "A morning panorama over Airakty, then Tuzbair salt marsh with its "
                        "white plains and natural arch. Continue to the Karaman-Ata necropolis "
                        "and underground mosque, and finish at Ybykty-Sai canyon with an "
                        "evening camp under the stars.",
            },
            {
                "n": 3,
                "title": "Ybykty-Sai • Bozzhyra • Kyzylkup",
                "note": "Martian panorama • Dragon's Ridge • lower Bozzhyra",
                "image": "routes/route03.jpg",
                "desc": "From Ybykty-Sai towards Bozzhyra: Martian panorama, Dragon's Ridge and "
                        "the lower valley. The day finishes at the colourful Kyzylkup tract, "
                        "known as the Mangystau Tiramisu.",
            },
            {
                "n": 4,
                "title": "Kyzylkup • Bokty • Tuyesu • Aktau",
                "note": "Kyzylkup • Mount Bokty • Tuyesu sand dunes",
                "image": "routes/route04.jpg",
                "desc": "Morning at Kyzylkup, then Mount Bokty for panoramic views and the "
                        "Tuyesu sand dunes for a short walk and photo session. After lunch, "
                        "return to Aktau.",
            },
        ],
    },

    "day5": {
        "label": {"en": "Five day vacation", "kz": "Бес күндік демалыс",
                  "ru": "Пятидневный отдых", "zh": "五日假期"},
        "unit": "day",
        "items": [
            {
                "n": 1,
                "title": "Aktau • Karamsai • Shakpak-Ata • Torysh • Kokala • Sherkala • Airakty",
                "note": "Airakty Valley of Castles • overnight",
                "image": "routes/route01.jpg",
                "desc": "Meet your guide in Aktau. Karamsai canyon, the Shakpak-Ata underground "
                        "mosque, the Torysh stone ball valley, Kokala and Sherkala mountain. "
                        "Dinner and overnight at the Airakty Valley of Castles.",
            },
            {
                "n": 2,
                "title": "Airakty • Tuzbair • Kogez",
                "note": "Tuzbair salt marsh • natural arch • yurt camp",
                "image": "routes/route02.jpg",
                "desc": "A morning hike through Airakty, then Tuzbair salt marsh with its white "
                        "plains and natural arch. Dinner and overnight at the Kogez yurt camp.",
            },
            {
                "n": 3,
                "title": "Karaman-Ata • Ybykty-Sai • Kyzylkup",
                "note": "Underground mosque • porous gorge • Tiramisu",
                "image": "routes/route03.jpg",
                "desc": "Karaman-Ata necropolis and underground mosque, then Ybykty-Sai canyon "
                        "and its porous gorge. The day ends among the red and white hills of "
                        "Kyzylkup, with a night at camp.",
            },
            {
                "n": 4,
                "title": "Kyzylkup • Bokty • Bozzhyra",
                "note": "Martian panorama • Dragon's Ridge • camp",
                "image": "routes/route04.jpg",
                "desc": "Morning at Kyzylkup, then Mount Bokty and on to Bozzhyra for the "
                        "Martian panorama and Dragon's Ridge. Camp near the cliffs.",
            },
            {
                "n": 5,
                "title": "Bozzhyra • Tuyesu • Karagiye • Aktau",
                "note": "Fangs • sand dunes • camel farm • Karagiye",
                "image": "routes/route05.jpg",
                "desc": "Start at the Bozzhyra Fangs viewpoint, then the Tuyesu sand dunes and "
                        "a camel farm with traditional local products. On the way back, a stop "
                        "at the Karagiye depression before returning to Aktau.",
            },
        ],
    },

    "day6": {
        "label": {"en": "Six day grand tour", "kz": "Алты күндік үлкен тур",
                  "ru": "Шестидневный гранд-тур", "zh": "六日全景之旅"},
        "unit": "day",
        "items": [
            {
                "n": 1,
                "title": "Aktau • Zhygylgan • Karamsai • Shakpak-Ata",
                "note": "Fallen Land • Shakpak-Ata • Kogez yurt camp",
                "image": "routes/route01.jpg",
                "desc": "Meet your guide in Aktau, then the Zhygylgan sinkhole known as the "
                        "Fallen Land, Karamsai gorge and the Shakpak-Ata underground mosque. "
                        "The day ends at the Kogez yurt camp.",
            },
            {
                "n": 2,
                "title": "Akespe • Torysh • Kokala • Sherkala • Airakty",
                "note": "Torysh stone balls • Kokala • Airakty",
                "image": "routes/route02.jpg",
                "desc": "Depart after breakfast towards Akespe, then the Torysh valley and its "
                        "giant stone concretions. Through Kokala to Sherkala mountain, "
                        "finishing at the Airakty Valley of Castles.",
            },
            {
                "n": 3,
                "title": "Karatau Baykisi • Tuzbair",
                "note": "Gorge • Tuzbair salt marsh",
                "image": "routes/route03.jpg",
                "desc": "The Karatau Baykisi gorge with a walk and photo session among the rock "
                        "formations, then Tuzbair salt marsh and its white plains framed by "
                        "limestone cliffs.",
            },
            {
                "n": 4,
                "title": "Senek • Bokty • Kyzylkup",
                "note": "Sand dunes • Mount Bokty • red and white hills",
                "image": "routes/route04.jpg",
                "desc": "The Senek sand dunes, then Mount Bokty — the striped pyramid rising "
                        "above the steppe — and finally Kyzylkup with its red and white "
                        "geological layers.",
            },
            {
                "n": 5,
                "title": "Bozzhyra • Mars panorama • Dragon Crest • Dragon Fangs",
                "note": "Full day in Bozzhyra • overnight tent camp",
                "image": "routes/route05.jpg",
                "desc": "A full day in Bozzhyra: the Martian panorama, Dragon Crest and the "
                        "Dragon Fangs viewpoint above the cliffs. Overnight tent camp.",
            },
            {
                "n": 6,
                "title": "Ybykty-Sai • Karaman-Ata • Aktau",
                "note": "Canyon • underground mosque • return to Aktau",
                "image": "routes/route06.jpg",
                "desc": "Ybykty-Sai canyon, then the Karaman-Ata underground mosque and "
                        "necropolis with the final photo stops of the expedition, before the "
                        "return journey to Aktau.",
            },
        ],
    },
}