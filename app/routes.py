import os
import re

from math import ceil
from datetime import datetime, date, timedelta
from functools import wraps
from urllib.parse import urlparse

from flask import (
    send_from_directory,
    abort,
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
    current_app,
)

from markupsafe import Markup, escape

from . import db
from .models import SiteSetting, Tour, TourRoute, Booking, Review

try:
    from .models import GalleryImage
except ImportError:          # ескі models.py — галерея бумалардан оқылады
    GalleryImage = None

# Telegram хабарламасы. Файл жоқ болса да сайт жұмыс істей береді.
try:
    from . import telegram_notify
except ImportError:
    telegram_notify = None


# =========================================================
# LOGIN REQUIRED
# =========================================================

def login_required(f):

    @wraps(f)
    def decorated_function(*args, **kwargs):

        if not session.get("admin_logged_in"):
            return redirect(
                url_for("admin.login")
            )

        return f(*args, **kwargs)

    return decorated_function


# =========================================================
# BLUEPRINTS
# =========================================================

site_bp = Blueprint("site", __name__)
admin_bp = Blueprint("admin", __name__)


# =========================================================
# SITE SETTINGS
# =========================================================

def settings():
    return {
        x.key: x.value
        for x in SiteSetting.query.all()
    }


# =========================================================
# LANGUAGES
# =========================================================
# html — <html lang="..."> үшін ДҰРЫС код.
# Қазақ тілінің коды "kk", "kz" емес (kz — ел коды).

LANGUAGES = [
    {"code": "kz", "html": "kk",      "label": "KZ",    "name": "Қазақша"},
    {"code": "ru", "html": "ru",      "label": "RU",    "name": "Русский"},
    {"code": "en", "html": "en",      "label": "EN",    "name": "English"},
    {"code": "it", "html": "it",      "label": "IT",    "name": "Italiano"},
    {"code": "fr", "html": "fr",      "label": "FR",    "name": "Français"},
    {"code": "pl", "html": "pl",      "label": "PL",    "name": "Polski"},
    {"code": "ja", "html": "ja",      "label": "日本語", "name": "日本語"},
    {"code": "zh", "html": "zh-Hans", "label": "中文",   "name": "中文"},
]

LANGUAGE_CODES = [x["code"] for x in LANGUAGES]

# Сайт алғаш ашылғанда қай тіл тұрады
DEFAULT_LANGUAGE = "en"


def html_lang(code):
    for x in LANGUAGES:
        if x["code"] == code:
            return x["html"]
    return "en"


# =========================================================
# HELPERS
# =========================================================

def safe_next(target):
    """
    Ашық редиректтен қорғау.
    ?next=https://evil.com сияқты сыртқы сілтемені қабылдамайды.
    """
    if not target or not target.startswith("/") or target.startswith("//"):
        return "/"

    parsed = urlparse(target)

    if parsed.scheme or parsed.netloc:
        return "/"

    return target


def price_number(value):
    """
    Tour.price — мәтін өріс (админкада "190 000 ₸" деп жазылуы мүмкін).
    Одан таза санды шығарамыз: "190 000 ₸" -> 190000
    """
    digits = re.sub(r"[^\d]", "", str(value or ""))
    return int(digits) if digits else 0


def duration_days(duration):
    """
    "3 күн", "2/1 ночь", "10 days" -> 3, 2, 10
    Ескі кодта duration|first == '1' деп бірінші СИМВОЛҒА қаралатын,
    сондықтан "10 days" бір күндік тур болып саналатын.
    """
    match = re.search(r"\d+", str(duration or ""))
    return int(match.group()) if match else 0


def money(value):
    """190000 -> '190 000'"""
    try:
        return "{:,.0f}".format(float(value or 0)).replace(",", " ")
    except (TypeError, ValueError):
        return "—"


def nl2br(value):
    """
    Жол ауыстыруды <br> тегіне айналдырады.

    Маңызды: escape() қайтаратын Markup объектісінің .replace() әдісі
    қосылатын мәтінді ҚАЙТА экрандайды — сондықтан "<br>" дегеніміз
    "&lt;br&gt;" болып шығып кететін. Сол себепті алдымен қарапайым
    жолға айналдырамыз, ауыстырамыз, сосын ғана Markup жасаймыз.
    """
    from markupsafe import Markup, escape

    text = str(escape(value or ""))

    for tag in ("&lt;br&gt;", "&lt;br/&gt;", "&lt;br /&gt;"):
        text = text.replace(tag, "<br>")

    text = text.replace("\\n", "\n").replace("\n", "<br>")

    return Markup(text)


def localize(value, language, fallback="en"):
    """
    Мәтін жай жол да, {"en": ..., "kz": ...} сөздігі де бола алады.
    """
    if isinstance(value, dict):
        return value.get(language) or value.get(fallback) or ""
    return value or ""


def _real_static_name(name):
    """
    static/ ішінен файлды ҮЛКЕН-КІШІ ӘРІПКЕ ҚАРАМАЙ табады да,
    оның нақты атауын қайтарады. Табылмаса — None.

    Не үшін: Windows-та IMG_3077.MP4 пен img_3077.mp4 — бір файл,
    ал Linux серверде (Render, PythonAnywhere) — екі бөлек файл.
    Компьютерде жұмыс істеген сайт серверде видеосыз қалатын.
    """
    try:
        folder = current_app.static_folder
    except RuntimeError:
        return name

    if not folder or not name:
        return None

    exact = os.path.join(folder, name.replace("/", os.sep))
    if os.path.exists(exact):
        return name

    # әр бөлікті жеке іздейміз: "Gallery/1/IMG.JPG" → "gallery/1/img.jpg"
    current = folder
    found_parts = []

    for part in name.replace("\\", "/").split("/"):
        if not part:
            continue
        try:
            entries = os.listdir(current)
        except OSError:
            return None

        match = next((e for e in entries if e.lower() == part.lower()), None)
        if match is None:
            return None

        found_parts.append(match)
        current = os.path.join(current, match)

    return "/".join(found_parts)


def _local_file_exists(name):
    """static/ ішінде мұндай файл бар ма? (үлкен-кіші әріпке қарамайды)"""
    try:
        current_app.static_folder
    except RuntimeError:
        return True          # контекст жоқ — тексере алмаймыз, сеніп өтеміз

    return _real_static_name(name) is not None


def asset(filename):
    """
    static файлына нұсқа нөмірін қосады: site.css?v=1789465022

    Не үшін: браузер (әсіресе iPhone Safari) CSS-ті кэштеп қояды да,
    файлды өзгертсең де ескісін көрсете береді. Нөмір файлдың
    өзгерту уақытынан алынады — файл өзгерсе, сілтеме де өзгереді,
    браузер жаңасын жүктейді.
    """
    try:
        path = os.path.join(current_app.static_folder, filename)
        stamp = int(os.path.getmtime(path))
    except (OSError, RuntimeError, TypeError):
        return url_for("static", filename=filename)

    return url_for("static", filename=filename, v=stamp)


def media_url(value, default=""):
    """
    Админкадағы жол әртүрлі жазылуы мүмкін:

        IMG_3077.MP4                -> /static/IMG_3077.MP4
        /static/IMG_3077.MP4        -> сол күйі
        https://cdn.site.com/a.mp4  -> сол күйі

    Бұзылған мән келсе (мысалы "https:98751290-5a8f..." сияқты
    жартыкеш сілтеме) немесе файл static/ ішінде жоқ болса,
    әдепкі файлға қайтады. Сондықтан 404 шықпайды.
    """
    value = (value or "").strip()

    def broken(text):
        if not text:
            return True
        # "https:xxxx" — қос сызықсыз жартыкеш сілтеме
        if text.startswith(("http:", "https:")) and not text.startswith(("http://", "https://")):
            return True
        return False

    if broken(value):
        value = ""

    if value:
        # Толық сыртқы сілтеме немесе абсолют жол — сол күйі
        if value.startswith(("http://", "https://", "//")):
            return value

        if value.startswith("/"):
            return value

        real = _real_static_name(value)
        if real:
            return url_for("static", filename=real)

        # Файл жоқ: әдепкіге түсеміз
        value = ""

    if default:
        real = _real_static_name(default)
        if real:
            return url_for("static", filename=real)

    return ""


def static_url(value):
    """Сурет жолын дұрыс URL-ге айналдырады."""
    if not value:
        return ""

    if value.startswith(("http://", "https://", "/")):
        return value

    return url_for("static", filename=value)


# =========================================================
# PACKAGES: BASIC / PLUS / DELUXE
# =========================================================
# Айырмасы: баға + фото / дрон / жеке гид.
#
# multiplier — тур бағасына көбейткіш. Пайызбен істелген себебі:
# 1 күндік турдағы фото қызметі мен 6 күндіктегі бірдей болмайды.

PACKAGES = [
    {
        "code": "basic",
        "name": "BASIC",
        "multiplier": 1.00,
        "popular": False,
        "tagline": {
            "kz": "Маршруттың өзі — сапалы деңгейде.",
            "ru": "Сам маршрут, без лишнего.",
            "en": "The route itself, done properly.",
            "zh": "纯粹的路线体验。",
        },
        "features": [
            {"ru": "Трансфер из отеля (только в Актау)",
             "en": "Hotel pick-up (Aktau only)",
             "kz": "Қонақүйден трансфер (тек Ақтауда)",
             "zh": "酒店接送（仅限阿克套）"},
            {"ru": "Внедорожник 4×4 с кондиционером",
             "en": "4×4 vehicle with air conditioning",
             "kz": "Кондиционері бар 4×4 көлік",
             "zh": "配备空调的四驱越野车"},
            {"ru": "Комфортное снаряжение для кемпинга",
             "en": "Comfortable camping equipment",
             "kz": "Жайлы кемпинг жабдығы",
             "zh": "舒适的露营装备"},
            {"ru": "3-разовое питание",
             "en": "Three meals a day",
             "kz": "Күніне үш мезгіл тамақ",
             "zh": "一日三餐"},
            {"ru": "Вода (1 л на человека в день)",
             "en": "Water (1 l per person per day)",
             "kz": "Су (адамға күніне 1 л)",
             "zh": "饮用水（每人每天 1 升）"},
            {"ru": "Туристическая страховка",
             "en": "Travel insurance",
             "kz": "Туристік сақтандыру",
             "zh": "旅游保险"},
        ],
    },
    {
        "code": "plus",
        "name": "PLUS",
        "multiplier": 1.25,
        # "Ең сұранысқа ие" белгісі. Кейін керек болса True қой.
        "popular": False,
        "tagline": {
            "kz": "Basic-тегінің бәрі, үстіне сапарыңыздың нағыз суреттері.",
            "ru": "Всё из Basic плюс настоящие фото вашей поездки.",
            "en": "Everything in Basic, plus real photos of your trip.",
            "zh": "包含 Basic 全部内容，另加专业旅拍。",
        },
        "features": [
            {"ru": "Трансфер из аэропорта",
             "en": "Airport transfer",
             "kz": "Әуежайдан трансфер",
             "zh": "机场接送"},
            {"ru": "Встреча в отеле",
             "en": "Meeting at your hotel",
             "kz": "Қонақүйде қарсы алу",
             "zh": "酒店迎接"},
            {"ru": "Внедорожник 4×4 с кондиционером",
             "en": "4×4 vehicle with air conditioning",
             "kz": "Кондиционері бар 4×4 көлік",
             "zh": "配备空调的四驱越野车"},
            {"ru": "Комфортное туристическое снаряжение",
             "en": "Comfortable travel equipment",
             "kz": "Жайлы туристік жабдық",
             "zh": "舒适的旅行装备"},
            {"ru": "3-разовое питание",
             "en": "Three meals a day",
             "kz": "Күніне үш мезгіл тамақ",
             "zh": "一日三餐"},
            {"ru": "Вода (1 л на человека в день)",
             "en": "Water (1 l per person per day)",
             "kz": "Су (адамға күніне 1 л)",
             "zh": "饮用水（每人每天 1 升）"},
            {"ru": "Туристическая страховка",
             "en": "Travel insurance",
             "kz": "Туристік сақтандыру",
             "zh": "旅游保险"},
            {"ru": "Туалет для кемпинга",
             "en": "Camping toilet",
             "kz": "Кемпинг дәретханасы",
             "zh": "露营厕所"},
            {"ru": "Дрон для видео",
             "en": "Drone filming",
             "kz": "Видеоға арналған дрон",
             "zh": "无人机拍摄"},
        ],
    },
    {
        "code": "deluxe",
        "name": "DELUXE",
        "multiplier": 1.60,
        "popular": False,
        "tagline": {
            "kz": "Бөлек жеке гид және толық түсірілім тобы.",
            "ru": "Отдельный гид и полноценная съёмочная группа.",
            "en": "A separate guide and a full film crew for your trip.",
            "zh": "专属向导与完整摄制团队。",
        },
        "features": [
            {"ru": "Трансфер из аэропорта",
             "en": "Airport transfer",
             "kz": "Әуежайдан трансфер",
             "zh": "机场接送"},
            {"ru": "Трансфер из отеля",
             "en": "Hotel transfer",
             "kz": "Қонақүйден трансфер",
             "zh": "酒店接送"},
            {"ru": "Внедорожник 4×4 с кондиционером",
             "en": "4×4 vehicle with air conditioning",
             "kz": "Кондиционері бар 4×4 көлік",
             "zh": "配备空调的四驱越野车"},
            {"ru": "Улучшенное снаряжение для кемпинга",
             "en": "Upgraded camping equipment",
             "kz": "Жақсартылған кемпинг жабдығы",
             "zh": "升级版露营装备"},
            {"ru": "3 блюда от шеф-повара в день",
             "en": "Three chef-prepared meals a day",
             "kz": "Күніне аспаз дайындаған 3 тағам",
             "zh": "每天三道主厨料理"},
            {"ru": "Вода (1 л на человека в день)",
             "en": "Water (1 l per person per day)",
             "kz": "Су (адамға күніне 1 л)",
             "zh": "饮用水（每人每天 1 升）"},
            {"ru": "Туристическая страховка",
             "en": "Travel insurance",
             "kz": "Туристік сақтандыру",
             "zh": "旅游保险"},
            {"ru": "Местный англоговорящий гид",
             "en": "Local English-speaking guide",
             "kz": "Ағылшын тілді жергілікті гид",
             "zh": "当地英语向导"},
            {"ru": "Туалет для кемпинга",
             "en": "Camping toilet",
             "kz": "Кемпинг дәретханасы",
             "zh": "露营厕所"},
            {"ru": "Душ для кемпинга",
             "en": "Camping shower",
             "kz": "Кемпинг душы",
             "zh": "露营淋浴"},
            {"ru": "Дрон для видео",
             "en": "Drone filming",
             "kz": "Видеоға арналған дрон",
             "zh": "无人机拍摄"},
            {"ru": "Генератор (зарядка устройств)",
             "en": "Generator for charging devices",
             "kz": "Генератор (құрылғы зарядтау)",
             "zh": "发电机（设备充电）"},
            {"ru": "Wi-Fi",
             "en": "Wi-Fi",
             "kz": "Wi-Fi",
             "zh": "无线网络"},
        ],
    },
]

PACKAGE_CODES = [x["code"] for x in PACKAGES]

DEFAULT_PACKAGE = "basic"


def get_package(code):
    for package in PACKAGES:
        if package["code"] == code:
            return package
    return PACKAGES[0]


# Әр турдың нақты бағасы (₸). Кілт — тур ұзақтығы (күн саны).
#
# Бұл кесте пайызбен есептеуден БАСЫМ. Мұнда жоқ тур болса ғана
# multiplier қолданылады.
#
# Бағаны өзгерту үшін тек осы сандарды түзетесің — басқа еш жерге
# тиюдің қажеті жоқ, сайт та, брондау беті де осыдан алады.

PACKAGE_PRICES = {

    2: {"basic":  295000, "plus":  375000, "deluxe":  500000},   # TWO DAY ULTIMATE
    3: {"basic":  435000, "plus":  555000, "deluxe":  760000},   # THREE DAY EXPEDITION
    4: {"basic":  585000, "plus":  745000, "deluxe": 1030000},   # FOUR DAY MANGYSTAU
    5: {"basic":  795000, "plus":  995000, "deluxe": 1360000},   # FIVE DAY VACATION
    6: {"basic": 1083000, "plus": 1323000, "deluxe": 1768000},   # SIX DAY GRAND TOUR

    # 1 күндік турда пакет жоқ — бағыт таңдалады, бағасы Tour.price
}


def package_price(base_price, package_code, days=None):
    """
    Пакеттің бағасы.

    1) PACKAGE_PRICES кестесінде бар болса — сол нақты сан
    2) Болмаса — базалық бағаны multiplier-ге көбейтеміз

    days: сан (2) немесе мәтін ("2 days", "2/1 ночь") — екеуі де жарайды.

    booking.html ішіндегі JS ДӘЛ ОСЫ логиканы қайталайды, сондықтан
    экрандағы баға мен базаға түсетін баға әрқашан сай келеді.
    """
    if isinstance(days, str):
        days = duration_days(days)

    try:
        days = int(days or 0)
    except (TypeError, ValueError):
        days = 0

    table = PACKAGE_PRICES.get(days)

    if table and package_code in table:
        return table[package_code]

    base = price_number(base_price) if not isinstance(base_price, (int, float)) else float(base_price)

    if not base or base <= 0:
        return 0

    total = base * get_package(package_code)["multiplier"]

    return int(round(total / 1000.0) * 1000)


def tour_package_price(tour, package_code):
    """
    Турдың пакет бағасы — ЕҢ АЛДЫМЕН админкада қойылғаны.

    1) Tour.price_basic / price_plus / price_deluxe — толтырылса, сол
    2) Болмаса — PACKAGE_PRICES кестесі (тур ұзақтығы бойынша)
    3) Ол да болмаса — Tour.price × пакет көбейткіші
    """
    if tour is None:
        return 0

    field = "price_{}".format(package_code)
    value = getattr(tour, field, 0) or 0

    try:
        value = int(value)
    except (TypeError, ValueError):
        value = 0

    if value > 0:
        return value

    return package_price(
        getattr(tour, "price", 0),
        package_code,
        getattr(tour, "duration", ""),
    )


# =========================================================
# TOUR ROUTES (дерекқордан)
# =========================================================
# Маршруттар TourRoute моделінде жатыр және админкадан өңделеді.
# Модельдегі өріс аттарын нақты білмегендіктен, ықтимал
# нұсқаларын кезекпен тексереміз — қайсысы бар болса, соны алады.

# =========================================================
# МАРШРУТ СУРЕТТЕРІ
# =========================================================
# Суретті қолмен тіркеудің қажеті жоқ: файлды дұрыс атаумен
# static/routes/ ішіне тастасаң, код өзі тауып алады.
#
#     static/routes/day1-01.jpg   ← 1 күндік турдың 1-бағыты
#     static/routes/day1-02.jpg   ← 1 күндік турдың 2-бағыты
#     static/routes/day2-01.jpg   ← 2 күндік турдың 1-күні
#     static/routes/day6-05.jpg   ← 6 күндік турдың 5-күні
#
# .jpg, .jpeg, .png, .webp — бәрі жарайды.
# Файл жоқ болса, карточка суретсіз көрінеді, қате шықпайды.

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")


def find_route_image(days, index):
    """static/routes/ ішінен келісілген атаумен сурет іздейді."""
    try:
        folder = os.path.join(current_app.static_folder, "routes")
    except RuntimeError:
        return ""

    if not os.path.isdir(folder):
        return ""

    names = (
        "day{}-{:02d}".format(days, index),
        "day{}-{}".format(days, index),
    )

    for name in names:
        for ext in IMAGE_EXTENSIONS:
            if os.path.exists(os.path.join(folder, name + ext)):
                return url_for("static", filename="routes/" + name + ext)

    return ""


def _pick(obj, names, default=""):
    for name in names:
        value = getattr(obj, name, None)
        if value:
            return value
    return default


def _int(value):
    digits = re.sub(r"[^\d]", "", str(value or ""))
    return int(digits) if digits else 0


# =========================================================
# ФОРС-МАЖОР ЖӘНЕ КИІМ ТӘРТІБІ
# =========================================================
# Жаңбырда баруға болмайтын орындар және жабық киім талап
# ететін орындар. Маршрут атауынан автоматты табылады.

RAIN_RESTRICTED = [
    "tuzbair", "tuzbayr", "тұзбайыр", "тузбаир", "тузбайыр",
    "bokty", "боқты", "бокты",
    "nizhny bozzhyra", "lower bozzhyra", "төменгі бозжыра", "нижняя бозжыра",
]

DRESS_CODE_PLACES = [
    "shakpak", "шақпақ", "шакпак",
    "karaman", "қараман", "караман",
    "沙克帕克",
]


def _has_word(text, words):
    text = str(text or "").lower()
    return any(word in text for word in words)


def route_flags(*texts):
    """Маршрут атауы мен сипаттамасынан ескертулерді табады."""
    joined = " ".join(str(t or "") for t in texts)
    return {
        "rain": _has_word(joined, RAIN_RESTRICTED),
        "dress_code": _has_word(joined, DRESS_CODE_PLACES),
    }


# =========================================================
# МАРШРУТТАР — ДАЙЫН ДЕРЕК
# =========================================================
# Дерекқорда (TourRoute) маршрут жоқ болса, осы қолданылады.
# Сондықтан әр турдың өз маршруты болады — база бос болса да.
#
# km — маршруттың шақырымы. НАҚТЫ САНДЫ ӨЗІҢ ЖАЗУЫҢ КЕРЕК:
# жалған қашықтық жазып қоймас үшін бәрін 0 қалдырдым,
# 0 болса — сайтта шақырым мүлдем көрсетілмейді.

ROUTE_FALLBACK = {

    # =====================================================
    # 1 КҮН — 5 бағыттың бірін таңдайды
    # =====================================================
    "day1": [
        {
            "title": {"ru": "Ыбыкты-Сай — Тузбаир",
                      "kz": "Ыбықты-Сай — Тұзбайыр",
                      "en": "Ybykty-Sai — Tuzbair",
                      "zh": "伊贝克提赛 — 图兹拜尔"},
            "km": 0,
            "desc": {"ru": "Каньон Ыбыкты-Сай и белые солончаки Тузбаира.",
                     "kz": "Ыбықты-Сай шатқалы және Тұзбайырдың ақ сорлары.",
                     "en": "The Ybykty-Sai canyon and the white salt flats of Tuzbair.",
                     "zh": "伊贝克提赛峡谷与图兹拜尔的白色盐滩。"},
        },
        {
            "title": {"ru": "Торыш — Тузбаир",
                      "kz": "Торыш — Тұзбайыр",
                      "en": "Torysh — Tuzbair",
                      "zh": "托雷什 — 图兹拜尔"},
            "km": 0,
            "note": {"ru": "При дождливой погоде вниз в Тузбаир не спускаемся.",
                     "kz": "Жаңбырлы ауа райында Тұзбайырға төмен түспейміз.",
                     "en": "In rainy weather we do not descend into Tuzbair.",
                     "zh": "雨天不下到图兹拜尔下部。"},
            "desc": {"ru": "Долина каменных шаров Торыш и солончак Тузбаир.",
                     "kz": "Торыштың тас шарлар алқабы және Тұзбайыр соры.",
                     "en": "The Torysh valley of stone balls and the Tuzbair salt marsh.",
                     "zh": "托雷什石球谷与图兹拜尔盐沼。"},
        },
        {
            "title": {"ru": "Капамсай • Шакпак-Ата • Торыш • Кокала • Шеркала • Айракты",
                      "kz": "Қапамсай • Шақпақ-Ата • Торыш • Көкала • Шерқала • Айрақты",
                      "en": "Kapamsai • Shakpak-Ata • Torysh • Kokala • Sherkala • Airakty",
                      "zh": "卡帕姆赛 • 沙克帕克-阿塔 • 托雷什 • 科卡拉 • 舍尔卡拉 • 艾拉克特"},
            "km": 0,
            "desc": {"ru": "Самый насыщенный однодневный маршрут: каньон, подземная мечеть, "
                           "каменные шары, Шеркала и долина замков Айракты.",
                     "kz": "Ең қанық бір күндік бағыт: шатқал, жерасты мешіті, тас шарлар, "
                           "Шерқала және Айрақтының қамалдар алқабы.",
                     "en": "The fullest one-day route: canyon, underground mosque, stone balls, "
                           "Sherkala and the Airakty Valley of Castles.",
                     "zh": "内容最丰富的一日线路：峡谷、地下清真寺、石球、舍尔卡拉与艾拉克特城堡谷。"},
        },
        {
            "title": {"ru": "Ыбыкты-Сай • Кызылкуп • Бозжыра",
                      "kz": "Ыбықты-Сай • Қызылқұп • Бозжыра",
                      "en": "Ybykty-Sai • Kyzylkup • Bozzhyra",
                      "zh": "伊贝克提赛 • 克孜勒库普 • 博兹日拉"},
            "km": 0,
            "desc": {"ru": "От каньона Ыбыкты-Сай к полосатым холмам Кызылкупа и скалам Бозжыры.",
                     "kz": "Ыбықты-Сай шатқалынан Қызылқұптың жолақты төбелері мен "
                           "Бозжыра жартастарына дейін.",
                     "en": "From the Ybykty-Sai canyon to the striped hills of Kyzylkup "
                           "and the cliffs of Bozzhyra.",
                     "zh": "从伊贝克提赛峡谷到克孜勒库普的条纹丘陵与博兹日拉悬崖。"},
        },
        {
            "title": {"ru": "Кызылкуп • Бокты • Бозжыра",
                      "kz": "Қызылқұп • Боқты • Бозжыра",
                      "en": "Kyzylkup • Bokty • Bozzhyra",
                      "zh": "克孜勒库普 • 博克特 • 博兹日拉"},
            "km": 0,
            "note": {"ru": "При дождливой погоде Бокты не посещаем.",
                     "kz": "Жаңбырлы ауа райында Боқтыға бармаймыз.",
                     "en": "In rainy weather Bokty is not visited.",
                     "zh": "雨天不前往博克特。"},
            "desc": {"ru": "Кызылкуп, полосатая гора Бокты и панорамы Бозжыры.",
                     "kz": "Қызылқұп, жолақты Боқты тауы және Бозжыра панорамалары.",
                     "en": "Kyzylkup, the striped Mount Bokty and the Bozzhyra panoramas.",
                     "zh": "克孜勒库普、条纹状的博克特山与博兹日拉全景。"},
        },
    ],

    # =====================================================
    # 2 КҮН
    # =====================================================
    "day2": [
        {
            "title": "AKTAU • KARAMSAI • SHAKPAK-ATA • TORYSH • KOKALA • SHERKALA • AIRAKTY",
            "km": 0,
            "desc": "Karamsai canyon, the Shakpak-Ata underground mosque above the Caspian "
                    "coast, the Torysh stone ball valley, Kokala and Mount Sherkala. "
                    "Overnight at the Airakty Valley of Castles.",
        },
        {
            "title": "BOZZHYRA (2 TOP LOCATIONS) • BOKTY • KYZYLKUP (TIRAMISU)",
            "km": 0,
            "desc": "Two main Bozzhyra viewpoints, then Mount Bokty and the red and white "
                    "layers of Kyzylkup. Return to Aktau in the evening.",
        },
    ],

    # =====================================================
    # 3 КҮН
    # =====================================================
    "day3": [
        {
            "title": "AKTAU • KARAMSAI • SHAKPAK-ATA • TORYSH • KOKALA • SHERKALA • AIRAKTY",
            "km": 0,
            "desc": "Karamsai canyon, the Shakpak-Ata underground mosque, the Torysh valley, "
                    "Kokala and Sherkala. Overnight camp at Airakty.",
        },
        {
            "title": "AIRAKTY • BOZZHYRA",
            "km": 0,
            "desc": "A morning hike at Airakty, then Bozzhyra with the Martian panorama and "
                    "Dragon Ridge. Night at camp.",
        },
        {
            "title": "BOZZHYRA PANORAMA • BOKTY • KYZYLKUP • AKTAU",
            "km": 0,
            "desc": "The Bozzhyra viewpoints, Mount Bokty and Kyzylkup, then the return to Aktau.",
        },
    ],

    # =====================================================
    # 4 КҮН
    # =====================================================
    "day4": [
        {
            "title": "AKTAU • KARAMSAI • SHAKPAK-ATA • TORYSH • KOKALA • SHERKALA • AIRAKTY",
            "km": 0,
            "desc": "Karamsai canyon and the Shakpak-Ata underground mosque, the Torysh stone "
                    "ball valley, Kokala, Sherkala and Airakty.",
        },
        {
            "title": "AIRAKTY • TUZBAIR • KARAMAN-ATA • YBYKTY-SAI",
            "km": 0,
            "desc": "The Tuzbair salt marsh and its natural arch, the Karaman-Ata necropolis "
                    "and underground mosque, then camp at Ybykty-Sai canyon.",
        },
        {
            "title": "YBYKTY-SAI • BOZZHYRA (UPPER AND LOWER PANORAMAS) • KYZYLKUP",
            "km": 0,
            "desc": "Both the upper and lower Bozzhyra panoramas, finishing at the colourful "
                    "Kyzylkup tract.",
        },
        {
            "title": "KYZYLKUP • BOKTY • TUYESU (SAND DUNES) • AKTAU",
            "km": 0,
            "desc": "Kyzylkup, Mount Bokty and the Tuyesu sand dunes, then back to Aktau.",
        },
    ],

    # =====================================================
    # 5 КҮН
    # =====================================================
    "day5": [
        {
            "title": "AKTAU • KARAMSAI • SHAKPAK-ATA • TORYSH • KOKALA • SHERKALA • AIRAKTY",
            "km": 0,
            "desc": "Karamsai canyon, the Shakpak-Ata underground mosque, Torysh, Kokala and "
                    "Sherkala, with dinner and overnight at Airakty.",
        },
        {
            "title": "AIRAKTY • TUZBAYR • YURT CAMP KOGEZ",
            "km": 0,
            "desc": "A morning at Airakty, then the Tuzbayr salt marsh and its natural arch. "
                    "Night at the Kogez yurt camp.",
        },
        {
            "title": "YURT CAMP KOGEZ • KARAMAN-ATA • YBYKTY-SAI • KYZYLKUP",
            "km": 0,
            "desc": "The Karaman-Ata necropolis and underground mosque, Ybykty-Sai canyon and "
                    "the red and white hills of Kyzylkup.",
        },
        {
            "title": "KYZYLKUP • BOKTY • BOZZHYRA (2 TOP PANORAMAS + LOWER LOCATION)",
            "km": 0,
            "desc": "Mount Bokty, then both upper Bozzhyra panoramas and the lower location.",
        },
        {
            "title": "BOZZHYRA • TUYESU (SAND DUNES) • AKTAU",
            "km": 0,
            "desc": "A last morning at Bozzhyra, the Tuyesu sand dunes and the return to Aktau.",
        },
    ],

    # =====================================================
    # 6 КҮН
    # =====================================================
    "day6": [
        {
            "title": "AKTAU • ZHYGYLGAN • KAPAMSAI • SHAKPAK-ATA",
            "km": 0,
            "desc": "The Zhygylgan sinkhole known as the Fallen Land, Kapamsai gorge and the "
                    "Shakpak-Ata underground mosque.",
        },
        {
            "title": "AKESPE • TORYSH • KOKALA • SHERKALA • AIRAKTY",
            "km": 0,
            "desc": "Akespe, the Torysh valley of stone concretions, Kokala and Sherkala, "
                    "finishing at Airakty.",
        },
        {
            "title": "KARATAU BAYKISI • TUZBAYR",
            "km": 0,
            "desc": "The Karatau Baykisi gorge and the white plains of the Tuzbayr salt marsh.",
        },
        {
            "title": "SENEK (SAND DUNES) • BOKTY • KYZYLKUP",
            "km": 0,
            "desc": "The Senek sand dunes, Mount Bokty and the layers of Kyzylkup.",
        },
        {
            "title": "BOZZHYRA: MARS PANORAMA • DRAGON CREST • DRAGON FANGS",
            "km": 0,
            "desc": "A full day in Bozzhyra: the Mars panorama, Dragon Crest and Dragon Fangs.",
        },
        {
            "title": "YBYKTY-SAI • KARAMAN-ATA • AKTAU",
            "km": 0,
            "desc": "Ybykty-Sai canyon and the Karaman-Ata underground mosque, then the return "
                    "journey to Aktau.",
        },
    ],
}


def routes_for(tour):
    """
    Турдың маршруттарын қайтарады.

    1) Алдымен дерекқордан (TourRoute) — админкадан өңделетін маршруттар
    2) Базада жоқ болса — ROUTE_FALLBACK ішіндегі дайын маршруттар

    Сондықтан әр турдың ӨЗ маршруты болады, база бос болса да.
    """
    if tour is None:
        return []

    rows = (
        TourRoute.query
        .filter_by(tour_id=tour.id)
        .order_by(TourRoute.day_number, TourRoute.sort_order)
        .all()
    )

    items = []

    for index, row in enumerate(rows, start=1):

        title = _pick(row, ["title", "name", "route", "header"])
        desc = _pick(row, ["description", "text", "details", "content"])
        flags = route_flags(title, desc)

        items.append({
            "key": "route-{}".format(row.id),
            "n": getattr(row, "day_number", None) or index,
            "title": title,
            "note": _pick(row, ["note", "subtitle", "summary", "short_text"]),
            "desc": desc,
            "image": (
                static_url(_pick(row, ["image", "photo", "cover", "picture"]))
                or find_route_image(duration_days(getattr(tour, "duration", "")), index)
            ),
            "km": _int(_pick(row, ["km", "distance", "distance_km", "length"], 0)),
            "price": price_number(getattr(row, "price", "")),
            "rain": flags["rain"],
            "dress_code": flags["dress_code"],
        })

    if items:
        return items

    # --- дерекқорда маршрут жоқ: дайын деректер ---

    days = duration_days(getattr(tour, "duration", ""))

    for index, item in enumerate(ROUTE_FALLBACK.get("day{}".format(days), []), start=1):

        flags = route_flags(item["title"], item.get("desc", ""))

        items.append({
            "key": "route-d{}-{}".format(days, index),
            "n": index,
            "title": item["title"],
            "note": item.get("note", ""),
            "desc": item.get("desc", ""),
            "image": static_url(item.get("image", "")) or find_route_image(days, index),
            "km": item.get("km", 0),
            "price": price_number(item.get("price", 0)),
            "rain": flags["rain"],
            "dress_code": flags["dress_code"],
        })

    return items


def route_options(tour):
    """
    Бір күндік турда клиент 5 бағыттың БІРЕУІН таңдайды.
    Көп күндік турда бұл тізім бос — онда бәрі бірдей жүреді.
    """
    if duration_days(getattr(tour, "duration", "")) != 1:
        return []
    return routes_for(tour)


def has_route_choice(tour):
    return bool(route_options(tour))


def route_meta(tour):
    """
    Маршруттар "күн" бе, әлде бір күндік турдың "бағыттары" ма,
    жалпы шақырым қанша, ескерту керек пе — бәрі бір жерде.
    """
    items = routes_for(tour)
    days = duration_days(getattr(tour, "duration", ""))

    return {
        "unit": "day" if days > 1 else "route",
        "days": days,
        "total_km": sum(item["km"] for item in items),
        "has_rain": any(item["rain"] for item in items),
        "has_dress_code": any(item["dress_code"] for item in items),
    }
# =========================================================
# LANGUAGE
# =========================================================

@site_bp.get("/language/<lang>")
def set_language(lang):

    if lang in LANGUAGE_CODES:
        session["language"] = lang
        session.permanent = True

    return redirect(
        safe_next(request.args.get("next"))
    )


# =========================================================
# TOUR DURATION TRANSLATION
# =========================================================

def translate_duration(duration, language):
    """
    Алдымен қолмен жазылған сөздіктен іздейді.
    Табылмаса — саннан автоматты құрайды ("4 days" -> "4 күн / 3 түн").
    Бұрын табылмаған мән сол күйі шығатын.
    """
    duration = (duration or "").strip()

    translations = {
        "kz": {
            "5/4 ночь": "5 күн / 4 түн",
            "4/3 ночь": "4 күн / 3 түн",
            "3/2 ночь": "3 күн / 2 түн",
            "2/1 ночь": "2 күн / 1 түн",
            "1 день": "1 күн",
            "1/0 ночь": "1 күн",
            "1 DAY": "1 күн",
            "1 day": "1 күн",
            "1 DAY / 0 NIGHT": "1 күн",
            "1 day / 0 night": "1 күн",
        },

        "ru": {
            "5/4 ночь": "5/4 ночь",
            "4/3 ночь": "4/3 ночь",
            "3/2 ночь": "3/2 ночь",
            "2/1 ночь": "2/1 ночь",
            "1 день": "1 день",
            "1/0 ночь": "1 день",
            "1 DAY": "1 день",
            "1 day": "1 день",
            "1 DAY / 0 NIGHT": "1 день",
            "1 day / 0 night": "1 день",
        },

        "en": {
            "5/4 ночь": "5 days / 4 nights",
            "4/3 ночь": "4 days / 3 nights",
            "3/2 ночь": "3 days / 2 nights",
            "2/1 ночь": "2 days / 1 night",
            "1 день": "1 day",
            "1/0 ночь": "1 day",
            "1 DAY": "1 day",
            "1 day": "1 day",
            "1 DAY / 0 NIGHT": "1 day",
            "1 day / 0 night": "1 day",
        },

        "zh": {
            "5/4 ночь": "5天4晚",
            "4/3 ночь": "4天3晚",
            "3/2 ночь": "3天2晚",
            "2/1 ночь": "2天1晚",
            "1 день": "1天",
            "1/0 ночь": "1天",
            "1 DAY": "1天",
            "1 day": "1天",
            "1 DAY / 0 NIGHT": "1天",
            "1 day / 0 night": "1天",
        },
    }

    table = translations.get(language, translations["kz"])

    if duration in table:
        return table[duration]

    # --- сөздікте жоқ болса, саннан құраймыз ---

    days = duration_days(duration)

    if not days:
        return duration

    nights = max(days - 1, 0)

    if language == "zh":
        return "{}天{}晚".format(days, nights) if nights else "{}天".format(days)

    if language == "ja":
        return "{}日間{}泊".format(days, nights) if nights else "{}日間".format(days)

    if language == "kz":
        return "{} күн / {} түн".format(days, nights) if nights else "{} күн".format(days)

    if language == "ru":
        day_word = "дня" if 2 <= days <= 4 else "дней"
        night_word = "ночи" if 2 <= nights <= 4 else "ночей"
        return "{} {} / {} {}".format(days, day_word, nights, night_word) if nights \
            else "{} {}".format(days, day_word)

    day_word = "days" if days > 1 else "day"
    night_word = "nights" if nights > 1 else "night"

    return "{} {} / {} {}".format(days, day_word, nights, night_word) if nights \
        else "{} {}".format(days, day_word)

# =========================================================
# ҚОСЫМША АДАМ (топ 3 адамнан аспайды)
# =========================================================
# Бір топта / бір көлікте ең көбі 3 қонақ.
# 4-ші адамнан бастап әр адам үшін турдың ұзақтығына
# қарай қосымша ақы алынады.

MAX_PER_GROUP = 3

MAX_GUESTS = 6

MAX_GROUPS = 4          # ең көбі 4 көлік = 12 қонақ          # 3 негізгі + 3 қосымша

EXTRA_PERSON_PRICES = {
    1: 25000,
    2: 50000,
    3: 85000,
    4: 115000,
    5: 145000,
    6: 175000,
}


def extra_person_price(days):
    """Турдың ұзақтығына сай бір қосымша адамның бағасы."""
    days = int(days or 0)

    if days in EXTRA_PERSON_PRICES:
        return EXTRA_PERSON_PRICES[days]

    if days > 6:
        # 6 күннен ұзақ болса, соңғы қадаммен (30 000/күн) жалғастырамыз
        return EXTRA_PERSON_PRICES[6] + (days - 6) * 30000

    return 0


def extra_guests_count(guests):
    """3 адамнан асқан қонақ саны."""
    try:
        guests = int(guests or 0)
    except (TypeError, ValueError):
        return 0
    return max(guests - MAX_PER_GROUP, 0)


def groups_count(guests):
    """Қанша топ / көлік керек."""
    try:
        guests = int(guests or 1)
    except (TypeError, ValueError):
        guests = 1
    return max(1, -(-guests // MAX_PER_GROUP))      # жоғары дөңгелектеу


# =========================================================
# ҚОСЫМША ҚЫЗМЕТТЕР
# =========================================================
# per_day=True  -> баға әр күнге көбейтіледі
# per_day=False -> бір реттік төлем

SERVICES = [
    {
        "code": "starlink",
        "price": 15000,
        "per_day": True,
        "included_in": ["deluxe"],
        "name": {"kz": "Starlink интернет", "ru": "Интернет Starlink",
                 "en": "Starlink internet", "zh": "星链网络"},
    },
    {
        "code": "guide_lang",
        "price": 30000,
        "per_day": True,
        "included_in": ["deluxe"],
        "name": {"kz": "Ағылшын / қытай тілді гид",
                 "ru": "Англо- или китайскоговорящий гид",
                 "en": "English or Chinese speaking guide",
                 "zh": "英语或中文向导"},
    },
    {
        "code": "drone",
        "price": 30000,
        "per_day": True,
        "included_in": ["plus", "deluxe"],
        "name": {"kz": "Дронмен түсірілім", "ru": "Съёмка с дрона",
                 "en": "Drone filming", "zh": "无人机拍摄"},
    },
    {
        "code": "shower",
        "price": 20000,
        "per_day": True,
        "included_in": ["deluxe"],
        "name": {"kz": "Душ", "ru": "Душ", "en": "Shower", "zh": "淋浴"},
    },
    {
        "code": "toilet",
        "price": 10000,
        "per_day": True,
        "included_in": ["plus", "deluxe"],
        "name": {"kz": "Дала дәретханасы", "ru": "Полевой туалет",
                 "en": "Portable toilet", "zh": "移动厕所"},
    },
    {
        "code": "generator",
        "price": 15000,
        "per_day": True,
        "included_in": ["deluxe"],
        "name": {"kz": "Генератор (құрылғы зарядтау)",
                 "ru": "Генератор для зарядки устройств",
                 "en": "Camp generator for charging devices",
                 "zh": "营地发电机（设备充电）"},
    },
    {
        "code": "transfer",
        "price": 10000,
        "per_day": False,
        "included_in": ["plus", "deluxe"],
        "name": {"kz": "Әуежайдан трансфер", "ru": "Трансфер из аэропорта",
                 "en": "Airport transfer", "zh": "机场接送"},
    },
]

SERVICE_CODES = [x["code"] for x in SERVICES]


def get_service(code):
    for service in SERVICES:
        if service["code"] == code:
            return service
    return None


def service_price(service, days):
    """Қызметтің жалпы бағасы (күндік болса — күнге көбейтіледі)."""
    days = max(int(days or 1), 1)
    return service["price"] * days if service["per_day"] else service["price"]


def is_included(service, package_code):
    """Қызмет таңдалған пакетте бар ма?"""
    return package_code in (service.get("included_in") or [])


def services_for(package_code=None):
    """
    Шаблонға арналған тізім. Пакетте бар қызмет
    "included" деген белгімен келеді — екі рет төленбейді.
    """
    return [
        dict(service, included=is_included(service, package_code))
        for service in SERVICES
    ]


def services_total(codes, days, package_code=None):
    total = 0
    for code in codes or []:
        service = get_service(code)
        if service and not is_included(service, package_code):
            total += service_price(service, days)
    return total


# =========================================================
# ТУР БАҒАСЫНА НЕ КІРЕДІ
# =========================================================
# Мәтіндер TRANSLATIONS ішінде төрт тілде дайын тұр,
# мұнда тек ретін және қай турға жарайтынын анықтаймыз.

INCLUDED_ALWAYS = [
    "include_transfer",            # 4×4 трансфер
    "include_experienced_guide",   # тәжірибелі гид
    "include_entrance",            # кіру билеттері
    "include_snacks",              # тіскебасар мен сусын
    "include_water",               # ауыз су
]

INCLUDED_OVERNIGHT = [
    "include_tents",               # шатырлар
    "include_sleeping",            # ұйықтайтын қап, төсеніш
    "include_lighting",            # лагерь жарығы
    "include_camping",             # кемпинг жабдығы
    "include_refrigerator",        # тоңазытқыш
]


def included_keys(tour):
    """
    Бір күндік турда шатыр мен ұйықтайтын қап болмайды,
    сондықтан оларды тек түнейтін турларда көрсетеміз.
    """
    keys = list(INCLUDED_ALWAYS)

    if duration_days(getattr(tour, "duration", "")) > 1:
        keys += INCLUDED_OVERNIGHT

    return keys


# =========================================================
# КАРТА НҮКТЕЛЕРІ
# =========================================================
# Координаттар index.html ішінен осында көшірілді.
# aliases — маршрут атауынан осы жерді табу үшін: маршрутта
# "Шеркала" деп жазылса да, "Sherkala" деп жазылса да табылады.
#
# Жаңа нүкте қосу: атауын, координатын және барлық жазылу
# нұсқасын aliases-ке қосасың — картада өзі шығады.

MAP_POINTS = [
    {
        "key": "aktau", "name": "AKTAU", "lat": 43.6353, "lng": 51.1682,
        "aliases": ["aktau", "ақтау", "актау"],
        "text": {"kz": "Саяхаттың бастау нүктесі.", "ru": "Отправная точка путешествия.",
                 "en": "Starting point of the journey.", "zh": "旅程的起点。"},
    },
    {
        "key": "karamsai", "name": "KARAMSAI", "lat": 44.409437, "lng": 51.078703,
        "aliases": ["karamsai", "kapamsai", "қарамсай", "карамсай", "капамсай"],
        "text": {"kz": "Қарамсай шатқалы.", "ru": "Каньон Карамсай.",
                 "en": "Karamsai canyon.", "zh": "卡拉姆赛峡谷。"},
    },
    {
        "key": "shakpak", "name": "SHAKPAK-ATA", "lat": 44.433512, "lng": 51.139109,
        "aliases": ["shakpak", "шақпақ", "шакпак", "沙克帕克"],
        "text": {"kz": "Шақпақ-Ата жерасты мешіті.", "ru": "Подземная мечеть Шакпак-Ата.",
                 "en": "Shakpak-Ata underground mosque.", "zh": "沙克帕克-阿塔地下清真寺。"},
    },
    {
        "key": "torysh", "name": "TORYSH", "lat": 44.361259, "lng": 51.561843,
        "aliases": ["torysh", "торыш", "托雷什"],
        "text": {"kz": "Құпия тас шарлар алқабы.", "ru": "Долина загадочных каменных шаров.",
                 "en": "Valley of mysterious stone balls.", "zh": "神秘石球谷。"},
    },
    {
        "key": "kokala", "name": "KOKALA", "lat": 44.247312, "lng": 51.885687,
        "aliases": ["kokala", "көкала", "кокала", "科卡拉"],
        "text": {"kz": "Түрлі-түсті геологиялық құрылымдар.",
                 "ru": "Разноцветные геологические образования.",
                 "en": "Colourful geological formations.", "zh": "五彩缤纷的地质构造。"},
    },
    {
        "key": "sherkala", "name": "SHERKALA", "lat": 44.257088, "lng": 52.005609,
        "aliases": ["sherkala", "шерқала", "шеркала", "舍尔卡拉", "谢尔卡拉"],
        "text": {"kz": "Әйгілі Шеркала тауы.", "ru": "Знаменитая гора Шеркала.",
                 "en": "The famous Mount Sherkala.", "zh": "著名的谢尔卡拉山。"},
    },
    {
        "key": "airakty", "name": "AIRAKTY", "lat": 44.240437, "lng": 52.083562,
        "aliases": ["airakty", "ayrakty", "айрақты", "айракты", "艾拉克特"],
        "text": {"kz": "Айракты — Қамалдар алқабы.", "ru": "Айракты — Долина замков.",
                 "en": "Airakty — Valley of Castles.", "zh": "艾拉克特——城堡谷。"},
    },
    {
        "key": "bozzhyra", "name": "BOZZHYRA", "lat": 43.399588, "lng": 54.096484,
        "aliases": ["bozzhyra", "bozjyra", "бозжыра", "бозжира", "博兹日拉"],
        "text": {"kz": "Маңғыстаудың ең әйгілі ландшафттарының бірі.",
                 "ru": "Один из самых знаковых пейзажей Мангистау.",
                 "en": "One of the most iconic landscapes of Mangystau.",
                 "zh": "曼吉斯套最具标志性的景观之一。"},
    },
    {
        "key": "bokty", "name": "BOKTY", "lat": 43.422987, "lng": 53.799391,
        "aliases": ["bokty", "боқты", "бокты", "博克特"],
        "text": {"kz": "Бөкті тауы.", "ru": "Гора Бокты.",
                 "en": "Mount Bokty.", "zh": "博克特山。"},
    },
    {
        "key": "karaman-ata", "name": "KARAMAN-ATA", "lat": 43.899917, "lng": 51.872307,
        "aliases": ["karaman", "қараман", "караман"],
        "text": {"kz": "Қараман-Ата жерасты мешіті мен некрополі.",
                 "ru": "Подземная мечеть и некрополь Караман-Ата.",
                 "en": "Karaman-Ata underground mosque and necropolis.",
                 "zh": "卡拉曼-阿塔地下清真寺与墓地。"},
    },
    {
        "key": "kyzylkup", "name": "KYZYLKUP · TIRAMISU", "lat": 43.474438, "lng": 53.809484,
        "aliases": ["kyzylkup", "kyzykup", "қызылқұп", "кызылкуп", "克孜勒库普"],
        "text": {"kz": "Қызылкүп — Маңғыстау тирамисуы.",
                 "ru": "Кызылкуп — мангистауский тирамису.",
                 "en": "Kyzylkup — the Mangystau Tiramisu.", "zh": "克孜勒库普——曼吉斯套提拉米苏。"},
    },
{
        "key": "tuzbair", "name": "TUZBAIR", "lat": 44.047306, "lng": 53.225649,
        "aliases": ["tuzbair", "tuzbayr", "тұзбайыр", "тузбаир", "тузбайыр", "图兹拜尔"],
        "text": {"kz": "Тұзбайыр соры — ақ тұзды жазық пен әктас жартастар.",
                 "ru": "Солончак Тузбаир — белая равнина и меловые обрывы.",
                 "en": "Tuzbair salt marsh — white plains framed by limestone cliffs.",
                 "zh": "图兹拜尔盐沼——白色平原与石灰岩峭壁。"},
    },
    {
        "key": "ybykty-sai", "name": "YBYKTY-SAI", "lat": 43.934192, "lng": 51.724347,
        "aliases": ["ybykty", "ыбықты", "ыбыкты", "伊贝克提"],
        "text": {"kz": "Ыбықты-Сай шатқалы.",
                 "ru": "Каньон Ыбыкты-Сай.",
                 "en": "Ybykty-Sai canyon.",
                 "zh": "伊贝克提赛峡谷。"},
    },
    {
        "key": "akespe", "name": "AKESPE", "lat": 44.413904, "lng": 51.604118,
        "aliases": ["akespe", "ақеспе", "акеспе"],
        "text": {"kz": "Ақеспе — ақ бор жартастардың етегіндегі ауыл.",
                 "ru": "Акеспе — село у подножия белых меловых скал.",
                 "en": "Akespe — a village at the foot of white chalk cliffs.",
                 "zh": "阿克斯佩——白垩峭壁脚下的村庄。"},
    },
    {
        "key": "tuyesu", "name": "TUYESU DUNES", "lat": 43.372265, "lng": 53.391020,
        "aliases": ["tuyesu", "tuesu", "түйесу", "туесу", "тюесу"],
        "text": {"kz": "Түйесу құм төбелері.",
                 "ru": "Песчаные дюны Туйесу.",
                 "en": "Tuyesu sand dunes.",
                 "zh": "图耶苏沙丘。"},
    },
]


def points_for_tour(tour):
    """
    Турдың маршруттарынан картадағы нүктелерді табады.
    Реті сақталады: 1-күннен соңғы күнге дейін.
    """
    order = []

    for route in routes_for(tour):
        title = " ".join([
            str(localize(route.get("title"), "en")),
            str(route.get("title")),
        ]).lower()

        for point in MAP_POINTS:
            if point["key"] in order:
                continue
            for alias in point["aliases"]:
                if alias in title:
                    order.append(point["key"])
                    break

    return order


def find_point_image(point):
    """
    Нүктенің суреті. Екі жолы бар:
      1) MAP_POINTS ішінде "image" жазылса — сол
      2) Жазылмаса, static/map/<key>.jpg файлын іздейді

    Мысалы: static/map/bozzhyra.jpg  ->  BOZZHYRA нүктесінің суреті.
    .jpg, .jpeg, .png, .webp — бәрі жарайды. Файл жоқ болса,
    popup суретсіз шығады, қате болмайды.
    """
    if point.get("image"):
        return media_url(point["image"])

    try:
        folder = os.path.join(current_app.static_folder, "map")
    except RuntimeError:
        return ""

    if not os.path.isdir(folder):
        return ""

    for ext in IMAGE_EXTENSIONS:
        name = point["key"] + ext
        if os.path.exists(os.path.join(folder, name)):
            return url_for("static", filename="map/" + name)

    return ""


def map_data(tours, language):
    """Картаға арналған барлық дерек: нүктелер және тур бойынша сүзгі."""
    points = [
        {
            "key": p["key"],
            "name": p["name"],
            "lat": p["lat"],
            "lng": p["lng"],
            "text": localize(p["text"], language),
            "image": find_point_image(p),
        }
        for p in MAP_POINTS
    ]

    tour_list = []

    for tour in tours:
        keys = points_for_tour(tour)
        if keys:
            tour_list.append({
                "id": tour.id,
                "title": getattr(tour, "title", ""),
                "days": duration_days(getattr(tour, "duration", "")),
                "points": keys,
            })

    return {"points": points, "tours": tour_list}


# =========================================================
# ГАЛЕРЕЯ
# =========================================================
# static/gallery/ қалтасындағы суреттерді өзі тауып алады.
# Қанша файл тастасаң, сонша көрінеді — кодқа тиюдің қажеті жоқ.
#
# Реті: файл аты бойынша. Белгілі бір ретпен тұрғанын қаласаң,
# файлдарды 01-bozzhyra.jpg, 02-sherkala.jpg деп ата.

# =========================================================
# ГАЛЕРЕЯ: ҮШ БӨЛЕК БЛОК
# =========================================================
# Әр блоктың өз қалтасы бар, суреттер бір-біріне араласпайды:
#
#     static/gallery/1/   — сол жақтағы үлкен блок
#     static/gallery/2/   — оң жақ, үстіңгі
#     static/gallery/3/   — оң жақ, астыңғы
#
# Қалталар бос болса, бұрынғыдай static/gallery/ ішіндегі
# барлық сурет үш блокқа бөлініп көрсетіледі.

GALLERY_SLOTS = 3


def _slot_folder(slot):
    return os.path.join(current_app.static_folder, "gallery", str(slot))


def slot_images(slot):
    """Бір блоктың суреттері, файл аты бойынша реттелген."""
    try:
        folder = _slot_folder(slot)
    except RuntimeError:
        return []

    if not os.path.isdir(folder):
        return []

    names = sorted(
        name for name in os.listdir(folder)
        if name.lower().endswith(IMAGE_EXTENSIONS)
    )

    return [
        {
            "name": name,
            "url": url_for("static", filename="gallery/{}/{}".format(slot, name)),
            "label": "Mangystau",
        }
        for name in names
    ]


def db_slot_images(slot):
    """Базадағы (Cloudinary) суреттер — бір блок."""
    if GalleryImage is None:
        return []

    try:
        rows = (
            GalleryImage.query
            .filter_by(slot=slot)
            .order_by(GalleryImage.sort_order, GalleryImage.id)
            .all()
        )
    except Exception:
        return []

    return [
        {"id": r.id, "name": r.public_id or str(r.id), "url": r.url, "label": "Mangystau"}
        for r in rows
    ]


def gallery_uses_db():
    """Базада кемінде бір галерея суреті болса — бәрі базадан оқылады."""
    if GalleryImage is None:
        return False
    try:
        return GalleryImage.query.count() > 0
    except Exception:
        return False


def gallery_slots():
    """
    [[блок 1 суреттері], [блок 2], [блок 3]]

    1) Базада суреттер болса — солар (Cloudinary, ешқашан жоғалмайды)
    2) Болмаса — static/gallery/1, /2, /3 бумалары
    3) Олар да бос болса — жалпы static/gallery/ үшке бөлінеді
    """
    if gallery_uses_db():
        return [db_slot_images(i) for i in range(1, GALLERY_SLOTS + 1)]

    slots = [slot_images(i) for i in range(1, GALLERY_SLOTS + 1)]

    if any(slots):
        return slots

    flat = gallery_images(limit=24)

    if not flat:
        return [[], [], []]

    step = max(len(flat) // GALLERY_SLOTS, 1)
    result = []

    for i in range(GALLERY_SLOTS):
        shift = step * i
        result.append(flat[shift:] + flat[:shift])

    return result


def gallery_images(limit=12):
    try:
        folder = os.path.join(current_app.static_folder, "gallery")
    except RuntimeError:
        return []

    if not os.path.isdir(folder):
        return []

    names = sorted(
        name for name in os.listdir(folder)
        if name.lower().endswith(IMAGE_EXTENSIONS)
    )

    images = []

    for name in names[:limit]:
        # Файл атынан оқылатын тақырып жасаймыз:
        # "02-bozzhyra-sunset.jpg" -> "Bozzhyra sunset"
        label = os.path.splitext(name)[0]
        label = re.sub(r"^\d+[-_\s]*", "", label)
        label = label.replace("-", " ").replace("_", " ").strip()

        images.append({
            "url": url_for("static", filename="gallery/" + name),
            "label": label.capitalize() or "Mangystau",
        })

    return images


# =========================================================
# ЕЛ КОДТАРЫ
# =========================================================
# Телефон өрісіндегі тізім. Реті: алдымен Қазақстан мен көрші
# елдер, сосын туристер жиі келетін бағыттар, қалғаны әліпбимен.
#
# Жаңа ел қосу: тізімге бір жол қосасың — қалғанын код өзі істейді.

COUNTRY_CODES = [
    ("+7",   "🇰🇿", "Kazakhstan"),
    ("+7",   "🇷🇺", "Russia"),
    ("+996", "🇰🇬", "Kyrgyzstan"),
    ("+998", "🇺🇿", "Uzbekistan"),
    ("+992", "🇹🇯", "Tajikistan"),
    ("+993", "🇹🇲", "Turkmenistan"),
    ("+994", "🇦🇿", "Azerbaijan"),
    ("+995", "🇬🇪", "Georgia"),
    ("+374", "🇦🇲", "Armenia"),
    ("+375", "🇧🇾", "Belarus"),
    ("+380", "🇺🇦", "Ukraine"),
    ("+976", "🇲🇳", "Mongolia"),

    ("+90",  "🇹🇷", "Türkiye"),
    ("+86",  "🇨🇳", "China"),
    ("+81",  "🇯🇵", "Japan"),
    ("+82",  "🇰🇷", "South Korea"),
    ("+91",  "🇮🇳", "India"),
    ("+62",  "🇮🇩", "Indonesia"),
    ("+60",  "🇲🇾", "Malaysia"),
    ("+65",  "🇸🇬", "Singapore"),
    ("+66",  "🇹🇭", "Thailand"),
    ("+84",  "🇻🇳", "Vietnam"),
    ("+63",  "🇵🇭", "Philippines"),
    ("+92",  "🇵🇰", "Pakistan"),
    ("+880", "🇧🇩", "Bangladesh"),
    ("+977", "🇳🇵", "Nepal"),
    ("+94",  "🇱🇰", "Sri Lanka"),
    ("+93",  "🇦🇫", "Afghanistan"),
    ("+98",  "🇮🇷", "Iran"),
    ("+964", "🇮🇶", "Iraq"),
    ("+972", "🇮🇱", "Israel"),
    ("+962", "🇯🇴", "Jordan"),
    ("+961", "🇱🇧", "Lebanon"),
    ("+966", "🇸🇦", "Saudi Arabia"),
    ("+971", "🇦🇪", "UAE"),
    ("+974", "🇶🇦", "Qatar"),
    ("+973", "🇧🇭", "Bahrain"),
    ("+965", "🇰🇼", "Kuwait"),
    ("+968", "🇴🇲", "Oman"),

    ("+44",  "🇬🇧", "United Kingdom"),
    ("+49",  "🇩🇪", "Germany"),
    ("+33",  "🇫🇷", "France"),
    ("+39",  "🇮🇹", "Italy"),
    ("+34",  "🇪🇸", "Spain"),
    ("+351", "🇵🇹", "Portugal"),
    ("+31",  "🇳🇱", "Netherlands"),
    ("+32",  "🇧🇪", "Belgium"),
    ("+41",  "🇨🇭", "Switzerland"),
    ("+43",  "🇦🇹", "Austria"),
    ("+48",  "🇵🇱", "Poland"),
    ("+420", "🇨🇿", "Czechia"),
    ("+421", "🇸🇰", "Slovakia"),
    ("+36",  "🇭🇺", "Hungary"),
    ("+40",  "🇷🇴", "Romania"),
    ("+359", "🇧🇬", "Bulgaria"),
    ("+385", "🇭🇷", "Croatia"),
    ("+386", "🇸🇮", "Slovenia"),
    ("+381", "🇷🇸", "Serbia"),
    ("+30",  "🇬🇷", "Greece"),
    ("+46",  "🇸🇪", "Sweden"),
    ("+47",  "🇳🇴", "Norway"),
    ("+45",  "🇩🇰", "Denmark"),
    ("+358", "🇫🇮", "Finland"),
    ("+354", "🇮🇸", "Iceland"),
    ("+353", "🇮🇪", "Ireland"),
    ("+372", "🇪🇪", "Estonia"),
    ("+371", "🇱🇻", "Latvia"),
    ("+370", "🇱🇹", "Lithuania"),
    ("+373", "🇲🇩", "Moldova"),

    ("+1",   "🇺🇸", "United States"),
    ("+1",   "🇨🇦", "Canada"),
    ("+52",  "🇲🇽", "Mexico"),
    ("+55",  "🇧🇷", "Brazil"),
    ("+54",  "🇦🇷", "Argentina"),
    ("+56",  "🇨🇱", "Chile"),
    ("+57",  "🇨🇴", "Colombia"),
    ("+51",  "🇵🇪", "Peru"),

    ("+61",  "🇦🇺", "Australia"),
    ("+64",  "🇳🇿", "New Zealand"),

    ("+20",  "🇪🇬", "Egypt"),
    ("+212", "🇲🇦", "Morocco"),
    ("+216", "🇹🇳", "Tunisia"),
    ("+27",  "🇿🇦", "South Africa"),
    ("+254", "🇰🇪", "Kenya"),
    ("+234", "🇳🇬", "Nigeria"),
]


# =========================================================
# ВАЛЮТА
# =========================================================
# Курсты админкадан өзгертуге болады: "Настройки" → usd_rate.
# Бос болса, төмендегі әдепкі мән қолданылады.

DEFAULT_USD_RATE = 500


def usd_rate():
    """1 доллар неше теңге."""
    try:
        value = settings().get("usd_rate", "")
    except Exception:
        value = ""

    digits = re.sub(r"[^\d.]", "", str(value or ""))

    try:
        rate = float(digits)
    except ValueError:
        rate = 0

    return rate if rate > 0 else DEFAULT_USD_RATE


# =========================================================
# ТУР БЕТІНІҢ МӘТІНДЕРІ
# =========================================================
# Барлық турға ортақ. Аудармасын қосқың келсе, жолды сөздікке
# айналдыр — L() екеуін де түсінеді:
#     "text": {"en": "...", "ru": "...", "kz": "..."}

# --- Маршруттардың ҮСТІНДЕ: үш негізгі факт ---

OVERVIEW_HIGHLIGHTS = [
    {
        "label": "Departure",
        "text": "Guaranteed departure — even for one person",
    },
    {
        "label": "Distance",
        "text": "900+ km of on-road & off-road adventure",
    },
    {
        "label": "Transport",
        "text": "4WD off-road vehicles",
    },
]


# --- Маршруттардың АСТЫНДА, сол блок: кездесу және дайындық ---

ITINERARY_INTRO = {
    "title": "Meeting & preparation",
    "steps": [
        {
            "time": "08:30",
            "place": "Aktau airport",
            "text": "Our team will meet you at Aktau International Airport and "
                    "assist with your transfer to the starting point of the expedition.",
        },
        {
            "time": "09:00",
            "place": "Aktau hotels",
            "text": "Guests staying in Aktau hotels will be picked up directly "
                    "from their accommodation.",
        },
        {
            "time": "",
            "place": "Get ready for the journey",
            "text": "After meeting all travelers, we will gather together, make final "
                    "preparations, and begin our journey through the spectacular "
                    "landscapes of Mangystau.",
        },
    ],
}


# --- Маршруттардың АСТЫНДА, оң блок: не кіреді ---

INCLUDED_TEXT = [
    "Experience the raw beauty of Mangystau through a carefully organized adventure "
    "across its most remote and spectacular landscapes.",

    "Travel with an experienced local guide who knows the region, its roads, hidden "
    "places, and stories. Enjoy freshly prepared local meals throughout the journey "
    "and discover the warm hospitality of Mangystau.",

    "Your adventure includes comfortable camp accommodation, reliable 4WD transport, "
    "and everything you need to explore the desert, canyons, cliffs, and iconic "
    "landscapes of the region.",

    "Nature, adventure, local culture, and the freedom of the open road — brought "
    "together in one unforgettable Mangystau experience.",
]


# =========================================================
# ЖАЛПЫ БАҒА
# =========================================================

def booking_total(tour, package_code, groups, service_codes=None, days=None,
                  unit_price=None):
    """
    Жалпы баға = (тур × пакет) × ТОП САНЫ + қосымша қызметтер

    Бір топ = бір көлік = 3 қонаққа дейін.
    Екінші топ қосылса, тур бағасы толық тағы бір рет қосылады
    (295 000 → 590 000), өйткені бөлек көлік пен гид керек.

    booking.html ішіндегі JS ДӘЛ осылай есептейді.
    """
    service_codes = service_codes or []

    if days is None:
        days = duration_days(getattr(tour, "duration", "")) or 1

    try:
        groups = int(groups or 1)
    except (TypeError, ValueError):
        groups = 1

    groups = max(1, min(groups, MAX_GROUPS))

    # Бір күндік турда әр бағыттың өз бағасы болуы мүмкін.
    # unit_price берілсе, тур бағасының орнына сол алынады.
    if unit_price:
        one_group = int(round(float(unit_price) / 1000.0) * 1000)
    else:
        one_group = tour_package_price(tour, package_code)

    base = one_group * groups

    services = services_total(service_codes, days, package_code)

    return {
        "days": days,
        "one_group": one_group,
        "groups": groups,
        "base": base,
        "guests": groups * MAX_PER_GROUP,
        "extra_people": 0,
        "extra": 0,
        "services": services,
        "total": base + services,
    }


# =========================================================
# ЕРЕЖЕЛЕР МЕН ЕСКЕРТУЛЕР


# =========================================================
# TRANSLATIONS
# =========================================================

TRANSLATIONS = {

    # =====================================================
    # KAZAKH
    # =====================================================

    "kz": {

        "tours": "Турлар",
        "about": "Біз туралы",
        "gallery": "Галерея",
        "booking": "Брондау",
        "book": "Брондау",

        "hero_eyebrow": "ЖАБАЙЫ ТАБИҒАТ • МАҢҒЫСТАУ",
        "hero_explore": "Турларды зерттеу",
        "hero_gallery": "Галереяны көру",

        "popular": "ТАНЫМАЛ БАҒЫТТАР",
        "choose": "Өзіңіздің\nприключениеңізді таңдаңыз.",
        "discover": (
            "Ұмытылмас жерлерді ашыңыз. "
            "Шөл каньондары, таулар, үстірттер "
            "және Каспий теңізі."
        ),

        "reserve": "Брондау",

        "discover_title": "МАНГЫСТАУДЫ ЗЕРТТЕНІЗ",
        "discover_text": (
            "Маңғыстаудың жабайы табиғатын зерттеңіз — "
            "аңызға айналған Бозжыра жартастарынан "
            "шексіз шөлдер мен Каспий жағалауына дейін."
        ),

        "why": "НЕГЕ MANGYSTAU TOUR",

        "benefit_1_title": "Сенімді 4×4",
        "benefit_1_text": (
            "Маршруттарға дайындалған жайлы "
            "жол талғамайтын көліктер."
        ),

        "benefit_2_title": "Жергілікті гидтер",
        "benefit_2_text": (
            "Маңғыстаудың әр бұрышын білетін "
            "тәжірибелі гидтер."
        ),

        "benefit_3_title": "Комфорт",
        "benefit_3_text": (
            "Уайымсыз саяхат үшін қажеттінің "
            "бәрі қарастырылған."
        ),

        "benefit_4_title": "Қауіпсіздік",
        "benefit_4_text": (
            "Тексерілген маршруттар және "
            "мұқият сүйемелдеу."
        ),

        "moments_label": "МАҢҒЫСТАУ",
        "moments_title": "Есте қалатын\nсәттер.",
        "moments_text": (
            "Мұнда әрбір шақырым кино кадрындай көрінеді."
        ),

        "ready": "САЯХАТҚА ДАЙЫНСЫЗ БА?",
        "time": "Маңғыстауды\nашатын уақыт.",

        "booking_text": (
            "Өтінім қалдырыңыз. Менеджеріміз сізбен "
            "байланысып, қолайлы маршрут таңдауға көмектеседі."
        ),

        "name": "Атыңыз",
        "name_placeholder": "Атыңызды енгізіңіз",
        "phone": "Телефон / WhatsApp",
        "tour_select": "Турды таңдаңыз",
        "route_select": "Маршрутты таңдаңыз",
        "guests": "Қонақтар саны",
        "comment": "Пікір",
        "comment_placeholder": (
            "Саяхатыңыз туралы айтып беріңіз..."
        ),
        "send": "Өтінім жіберу",
        "wild_nature": "Жабайы табиғат. Нағыз эмоциялар.",

        "reviews": "Пікірлер",
        "reviews_title": "Саяхатшылардың\nпікірлері.",
        "reviews_text": (
            "Маңғыстауға барған қонақтардың әсерлері."
        ),

        "map_title": "МАҢҒЫСТАУДЫ\nКАРТАДАН АШЫҢЫЗ.",
        "map_text": (
            "Маңғыстаудың ең танымал табиғи орындарын "
            "бір картадан зерттеңіз."
        ),

        "tour_duration_label": "Ұзақтығы",
        "tour_transport": "Көлік",
        "tour_group": "Топ",
        "tour_region": "Аймақ",
        "one_day": "ONE DAY",

        "routes_title": "1 күн маршруттар",

        "route_1": "Ыбыкты-Сай — Тұзбайыр",
        "route_2": "Торыш — Тұзбайыр",
        "route_2_note": (
            "Жаңбырлы ауа райында Тұзбайырдың "
            "төменгі бөлігіне түспейміз."
        ),

        "route_3": (
            "Қапамсай — Шақпақ-Ата — Торыш — "
            "Көкала — Шерқала — Айрақты"
        ),

        "route_4": (
            "Ыбыкты-Сай — Қызылқұп — Бозжыра"
        ),

        "route_5": (
            "Қызылқұп — Боқты — Бозжыра"
        ),

        "route_5_note": (
            "Жаңбырлы ауа райында Боқтыға бармаймыз."
        ),

        "tour_price_note": (
            "Баға таңдалған маршрутқа байланысты."
        ),

        "tour_includes": "Тур бағасына кіреді",
        "include_4x4": "4×4 жол талғамайтын көлік",
        "include_guide": "Жергілікті гид",
        "include_support": "Маршрут бойынша сүйемелдеу",
        "include_water": "Ауыз су",

        "tour_2day_title": "2 КҮНДІК JEEP ЭКСПЕДИЦИЯСЫ",

        "tour_2day_description": (
            "Маңғыстаудың ең танымал табиғи орындары арқылы "
            "жол талғамайтын саяхат — жайлылық, қауіпсіздік "
            "және ұмытылмас көріністер."
        ),

        "price": "Баға",
        "per_tour": "тур үшін",
        "duration": "Ұзақтығы",
        "vehicle": "Көлік",
        "start_end": "Басталуы / аяқталуы",
        "distance": "Қашықтық",
        "itinerary": "Маршрут",
        "day": "КҮН",
        "meals": "Тамақтану",
        "stay": "Қону",

        "day1_route": (
            "АКТАУ • ҚАРАМСАЙ • ШАҚПАҚ-АТА • ТОРЫШ • "
            "КӨКАЛА • ШЕРҚАЛА • АЙРАҚТЫ"
        ),

        "day1_text": (
            "Қонақүйіңізден немесе Ақтау әуежайынан гидпен кездесесіз. "
            "Алғашқы аялдама — Қарамай каньоны. Кейін Каспий жағалауындағы "
            "бор жартастың ішіне қашалып жасалған Шақпақ-Ата жерасты "
            "мешітіне барамыз. Одан әрі мыңдаған дөңгелек тас "
            "конкрецияларымен әйгілі Торыш алқабына жол тартамыз. "
            "Шерқала тауына тоқтап, суретке түсеміз. Содан кейін "
            "қара жолмен Айрақтының Қамалдар алқабына барамыз."
        ),

        "day1_meals": "Жеңіл тіскебасар, кешкі ас",
        "day1_stay": "Жұлдыздар астындағы шатыр",

        "day2_route": (
            "БОЗЖЫРА • БОҚТЫ • ҚЫЗЫЛҚҰП"
        ),

        "day2_text": (
            "Таңертең ежелгі Тетис мұхитының қалдықтарынан қалыптасқан "
            "керемет панорамаларымен әйгілі Бозжыраға барамыз. "
            "Ауа райын ескеріп, жылы киім алыңыз — климат Ақтауға "
            "қарағанда 10–15°C өзгеше болуы мүмкін. Кейін дала "
            "ортасында жеке тұрған жолақты пирамида тәрізді Боқты "
            "тауына және бор мен темір қабаттары ерекше көрініс "
            "беретін Қызылқұп алқабына барамыз. Күн соңында "
            "Ақтауға қайтамыз."
        ),

        "day2_meals": "Таңғы ас, жеңіл түскі ас",
        "day2_stay": "Ақтау, кешкі уақыт",

        "what_included": "Тур бағасына кіреді",
        "additional": "Қосымша",

        "include_transfer": "4×4 трансфер",
        "include_experienced_guide": "Тәжірибелі гид",
        "include_entrance": "Барлық кіру билеттері",
        "include_snacks": "Тіскебасарлар мен сусындар",
        "include_tents": "Шатырлар",
        "include_sleeping": "Ұйықтайтын қаптар және төсеніштер",
        "include_lighting": "Лагерь жарықтандыруы",
        "include_camping": "Кемпинг жабдықтары",
        "include_refrigerator": "Тоңазытқыш",
        "include_drone": "Дронмен түсірілім",
        "include_photo": "Фото сүйемелдеу",

        "additional_guide": "Ағылшын тілінде сөйлейтін гид",
        "on_request": "сұраныс бойынша",
    },


    # =====================================================
    # RUSSIAN
    # =====================================================

    "ru": {

        "tours": "Туры",
        "about": "О нас",
        "gallery": "Галерея",
        "booking": "Бронирование",
        "book": "Забронировать",

        "hero_eyebrow": "ДИКАЯ ПРИРОДА • МАНГИСТАУ",
        "hero_explore": "Исследовать туры",
        "hero_gallery": "Смотреть галерею",

        "popular": "ПОПУЛЯРНЫЕ МАРШРУТЫ",
        "choose": "Выберите своё\nприключение.",
        "discover": (
            "Откройте места, которые невозможно забыть. "
            "Пустынные каньоны, горы, плато и Каспийское море."
        ),

        "reserve": "Забронировать",

        "discover_title": "ОТКРОЙТЕ МАНГИСТАУ",
        "discover_text": (
            "Исследуйте дикую природу Мангистау — "
            "от легендарных скал Бозжыры до бескрайних "
            "пустынь и побережья Каспийского моря."
        ),

        "why": "ПОЧЕМУ MANGYSTAU TOUR",

        "benefit_1_title": "Надёжные 4×4",
        "benefit_1_text": (
            "Комфортные внедорожники, подготовленные "
            "для маршрутов."
        ),

        "benefit_2_title": "Местные гиды",
        "benefit_2_text": (
            "Люди, которые знают каждый уголок Мангистау."
        ),

        "benefit_3_title": "Комфорт",
        "benefit_3_text": (
            "Всё необходимое для путешествия "
            "без лишних забот."
        ),

        "benefit_4_title": "Безопасность",
        "benefit_4_text": (
            "Проверенные маршруты и внимательное сопровождение."
        ),

        "moments_label": "MANGYSTAU",
        "moments_title": "Моменты,\nкоторые остаются.",
        "moments_text": (
            "Здесь каждый километр выглядит как кадр из фильма."
        ),

        "ready": "ГОТОВЫ К ПУТЕШЕСТВИЮ?",
        "time": "Время открыть\nМангистау.",

        "booking_text": (
            "Оставьте заявку. Наш менеджер свяжется "
            "с вами и поможет подобрать маршрут."
        ),

        "name": "Ваше имя",
        "name_placeholder": "Введите имя",
        "phone": "Телефон / WhatsApp",
        "tour_select": "Выберите тур",
        "route_select": "Выберите маршрут",
        "guests": "Количество гостей",
        "comment": "Комментарий",
        "comment_placeholder": (
            "Расскажите о вашем путешествии..."
        ),
        "send": "Отправить заявку",
        "wild_nature": "Дикая природа. Настоящие эмоции.",

        "reviews": "Отзывы",
        "reviews_title": "Отзывы\nпутешественников.",
        "reviews_text": (
            "Впечатления гостей, которые уже побывали в Мангистау."
        ),

        "map_title": "ОТКРОЙТЕ МАНГИСТАУ\nНА КАРТЕ.",
        "map_text": (
            "Исследуйте самые известные природные "
            "места Мангистау на одной карте."
        ),

        "tour_duration_label": "Продолжительность",
        "tour_transport": "Транспорт",
        "tour_group": "Группа",
        "tour_region": "Регион",
        "one_day": "ONE DAY",

        "routes_title": "Маршруты на 1 день",

        "route_1": "Ыбыкты-Сай — Тузбаир",
        "route_2": "Торыш — Тузбаир",
        "route_2_note": (
            "В дождливую погоду вниз в Тузбаир "
            "не спускаемся."
        ),

        "route_3": (
            "Капамсай — Шакпак-Ата — Торыш — "
            "Кокала — Шеркала — Айракты"
        ),

        "route_4": (
            "Ыбыкты-Сай — Кызылкуп — Бозжира"
        ),

        "route_5": (
            "Кызылкуп — Бокты — Бозжира"
        ),

        "route_5_note": (
            "В дождливую погоду Бокты не посещаем."
        ),

        "tour_price_note": (
            "Цена зависит от выбранного маршрута."
        ),

        "tour_includes": "В стоимость входит",
        "include_4x4": "Внедорожник 4×4",
        "include_guide": "Местный гид",
        "include_support": "Сопровождение по маршруту",
        "include_water": "Питьевая вода",

        "tour_2day_title": "2-ДНЕВНАЯ JEEP ЭКСПЕДИЦИЯ",

        "tour_2day_description": (
            "Путешествие по самым знаковым местам Мангистау — "
            "внедорожное приключение, комфорт, безопасность "
            "и незабываемые виды."
        ),

        "price": "Цена",
        "per_tour": "за тур",
        "duration": "Продолжительность",
        "vehicle": "Транспорт",
        "start_end": "Начало / конец",
        "distance": "Расстояние",
        "itinerary": "Маршрут",
        "day": "ДЕНЬ",
        "meals": "Питание",
        "stay": "Проживание",

        "day1_route": (
            "АКТАУ • КАРАМСАЙ • ШАКПАК-АТА • ТОРЫШ • "
            "КОКАЛА • ШЕРКАЛА • АЙРАКТЫ"
        ),

        "day1_text": (
            "Встреча с гидом у вашего отеля или в аэропорту Актау. "
            "Первая остановка — каньон Карамай. Затем посещаем "
            "подземную мечеть Шакпак-Ата, высеченную в меловой скале "
            "над побережьем Каспийского моря. Далее отправляемся "
            "в долину Торыш, знаменитую тысячами круглых каменных "
            "конкреций диаметром до 4 метров. После короткой остановки "
            "у горы Шеркала для фотографий продолжаем путь по грунтовой "
            "дороге в долину замков Айракты."
        ),

        "day1_meals": "Лёгкий перекус, ужин на месте",
        "day1_stay": "Палатка под звёздами",

        "day2_route": (
            "БОЗЖЫРА • БОКТЫ • КЫЗЫЛКУП"
        ),

        "day2_text": (
            "Утром отправляемся в урочище Бозжыра с фантастическими "
            "панорамными видами, сформированными остатками древнего "
            "океана Тетис. Следим за погодой и рекомендуем взять "
            "тёплую одежду — температура здесь может отличаться "
            "от Актау на 10–15°C. Далее посещаем гору Бокты — "
            "полосатую пирамиду, одиноко возвышающуюся над степью, "
            "и соседнее урочище Кызылкуп, где разноцветные слои "
            "мела и железа создают необычный пейзаж. "
            "В конце дня возвращаемся в Актау."
        ),

        "day2_meals": "Завтрак, лёгкий обед",
        "day2_stay": "Актау, вечер",

        "what_included": "В стоимость входит",
        "additional": "Дополнительно",

        "include_transfer": "Трансфер 4×4",
        "include_experienced_guide": "Опытный гид",
        "include_entrance": "Все входные билеты",
        "include_snacks": "Закуски и напитки",
        "include_tents": "Палатки",
        "include_sleeping": "Спальные мешки и коврики",
        "include_lighting": "Освещение лагеря",
        "include_camping": "Кемпинговое оборудование",
        "include_refrigerator": "Холодильник",
        "include_drone": "Съёмка с дрона",
        "include_photo": "Фотосопровождение",

        "additional_guide": "Англоговорящий гид",
        "on_request": "по запросу",
    },


    # =====================================================
    # ENGLISH
    # =====================================================

    "en": {

        "tours": "Tours",
        "about": "About Us",
        "gallery": "Gallery",
        "booking": "Booking",
        "book": "Book Now",

        "hero_eyebrow": "WILD NATURE • MANGYSTAU",
        "hero_explore": "Explore Tours",
        "hero_gallery": "View Gallery",

        "popular": "POPULAR ROUTES",
        "choose": "Choose your\nadventure.",
        "discover": (
            "Discover places you will never forget. "
            "Desert canyons, mountains, plateaus and the Caspian Sea."
        ),

        "reserve": "Book Now",

        "discover_title": "DISCOVER MANGYSTAU",
        "discover_text": (
            "Explore the wild landscapes of Mangystau — "
            "from the legendary Bozzhyra cliffs to endless "
            "deserts and the Caspian coast."
        ),

        "why": "WHY MANGYSTAU TOUR",

        "benefit_1_title": "Reliable 4×4",
        "benefit_1_text": (
            "Comfortable off-road vehicles prepared for our routes."
        ),

        "benefit_2_title": "Local Guides",
        "benefit_2_text": (
            "People who know every corner of Mangystau."
        ),

        "benefit_3_title": "Comfort",
        "benefit_3_text": (
            "Everything you need for a worry-free journey."
        ),

        "benefit_4_title": "Safety",
        "benefit_4_text": (
            "Verified routes and attentive support."
        ),

        "moments_label": "MANGYSTAU",
        "moments_title": "Moments\nthat stay.",
        "moments_text": (
            "Every kilometer here looks like a movie scene."
        ),

        "ready": "READY FOR THE JOURNEY?",
        "time": "Time to discover\nMangystau.",

        "booking_text": (
            "Leave a request. Our manager will contact you "
            "and help you choose the right route."
        ),

        "name": "Your Name",
        "name_placeholder": "Enter your name",
        "phone": "Phone / WhatsApp",
        "tour_select": "Choose a tour",
        "route_select": "Choose a route",
        "guests": "Number of guests",
        "comment": "Comment",
        "comment_placeholder": "Tell us about your trip...",
        "send": "Send Request",
        "wild_nature": "Wild nature. Real emotions.",

        "reviews": "Reviews",
        "reviews_title": "Traveler\nreviews.",
        "reviews_text": (
            "Experiences from guests who have explored Mangystau."
        ),

        "map_title": "DISCOVER MANGYSTAU\nON THE MAP.",
        "map_text": (
            "Explore the most iconic natural places "
            "of Mangystau on one map."
        ),

        "tour_duration_label": "Duration",
        "tour_transport": "Transport",
        "tour_group": "Group",
        "tour_region": "Region",
        "one_day": "ONE DAY",

        "routes_title": "1 Day Routes",

        "route_1": "Ybykty-Sai — Tuzbair",
        "route_2": "Torysh — Tuzbair",
        "route_2_note": (
            "In rainy weather, we do not descend "
            "to the lower part of Tuzbair."
        ),

        "route_3": (
            "Kapamsai — Shakpak-Ata — Torysh — "
            "Kokala — Sherkala — Ayrakty"
        ),

        "route_4": (
            "Ybykty-Sai — Kyzylkup — Bozzhyra"
        ),

        "route_5": (
            "Kyzylkup — Bokty — Bozzhyra"
        ),

        "route_5_note": (
            "In rainy weather, Bokty is not visited."
        ),

        "tour_price_note": (
            "The price depends on the selected route."
        ),

        "tour_includes": "Tour includes",
        "include_4x4": "4×4 off-road vehicle",
        "include_guide": "Local guide",
        "include_support": "Route support",
        "include_water": "Drinking water",

        "tour_2day_title": "2-DAY JEEP EXPEDITION",

        "tour_2day_description": (
            "Off-road adventure through Mangystau's most iconic "
            "landscapes — comfort, safety and unforgettable views."
        ),

        "price": "PRICE",
        "per_tour": "per tour",
        "duration": "DURATION",
        "vehicle": "VEHICLE",
        "start_end": "START / END",
        "distance": "DISTANCE",
        "itinerary": "ITINERARY",
        "day": "DAY",
        "meals": "MEALS",
        "stay": "STAY",

        "day1_route": (
            "AKTAU • KARAMSAI • SHAKPAK-ATA • TORYSH • "
            "KOKALA • SHERKALA • AIRAKTY"
        ),

        "day1_text": (
            "Meet your guide at your hotel or the Aktau airport. "
            "First stop at the Karamsai canyon, then the underground "
            "mosque of Shakpak-Ata carved into a chalk cliff above "
            "the Caspian coast. Continue to the Torysh Valley, famous "
            "for its thousands of round stone concretions up to "
            "4 meters in diameter. Continue to Mount Sherkala with "
            "a short stop for photos, then drive along a dirt road "
            "to the Airakty Valley of Castles."
        ),

        "day1_meals": "Light snack, dinner on site",
        "day1_stay": "Tent under the stars",

        "day2_route": (
            "BOZZHYRA • BOKTY • KYZYLKUP"
        ),

        "day2_text": (
            "In the morning you head to the Bozzhyra tract for "
            "fantastic panoramic views formed by the remains of "
            "the ancient Tethys Ocean. Keep an eye on the weather "
            "and bring warm clothes — the climate can differ by "
            "10–15°C from Aktau. Next, visit Mount Bokty, a striped "
            "pyramid rising alone above the steppe, and the neighbouring "
            "Kyzylkup tract, where colourful layers of chalk and iron "
            "create a mesmerizing landscape. Return to Aktau at the "
            "end of the day."
        ),

        "day2_meals": "Breakfast, light lunch",
        "day2_stay": "Aktau, evening",

        "what_included": "WHAT'S INCLUDED",
        "additional": "ADDITIONAL",

        "include_transfer": "4×4 transfer",
        "include_experienced_guide": "Experienced guide",
        "include_entrance": "All entrance fees",
        "include_snacks": "Snacks & drinks",
        "include_tents": "Tents",
        "include_sleeping": "Sleeping bags & sleeping mats",
        "include_lighting": "Camp lighting",
        "include_camping": "Camping equipment",
        "include_refrigerator": "Refrigerator",
        "include_drone": "Drone footage",
        "include_photo": "Photo support",

        "additional_guide": "English-speaking guide",
        "on_request": "on request",
    },


    # =====================================================
    # CHINESE
    # =====================================================

    "zh": {

        "tours": "旅游线路",
        "about": "关于我们",
        "gallery": "画廊",
        "booking": "预订",
        "book": "立即预订",

        "hero_eyebrow": "原野自然 • 曼吉斯套",
        "hero_explore": "探索旅行",
        "hero_gallery": "查看画廊",

        "popular": "热门路线",
        "choose": "选择你的\n冒险之旅。",
        "discover": (
            "探索令人难忘的地方：沙漠峡谷、山脉、高原和里海。"
        ),

        "reserve": "立即预订",

        "discover_title": "探索曼吉斯套",
        "discover_text": (
            "探索曼吉斯套的原始自然风光——"
            "从传奇的博兹日拉悬崖，到无尽的沙漠和里海海岸。"
        ),

        "why": "为什么选择 MANGYSTAU TOUR",

        "benefit_1_title": "可靠的4×4",
        "benefit_1_text": (
            "为越野路线准备的舒适四驱车。"
        ),

        "benefit_2_title": "当地向导",
        "benefit_2_text": (
            "熟悉曼吉斯套每一个角落的当地向导。"
        ),

        "benefit_3_title": "舒适体验",
        "benefit_3_text": (
            "轻松旅行所需的一切都已准备好。"
        ),

        "benefit_4_title": "安全保障",
        "benefit_4_text": (
            "经过验证的路线和全程细致陪同。"
        ),

        "moments_label": "MANGYSTAU",
        "moments_title": "难忘的\n旅途瞬间。",
        "moments_text": (
            "这里的每一公里都像电影中的画面。"
        ),

        "ready": "准备好出发了吗？",
        "time": "是时候探索\n曼吉斯套了。",

        "booking_text": (
            "提交申请，我们的经理会联系您并帮助您选择合适的路线。"
        ),

        "name": "您的姓名",
        "name_placeholder": "请输入姓名",
        "phone": "电话 / WhatsApp",
        "tour_select": "选择旅游线路",
        "route_select": "选择路线",
        "guests": "游客人数",
        "comment": "备注",
        "comment_placeholder": "告诉我们您的旅行计划...",
        "send": "提交申请",
        "wild_nature": "原野自然。真实感受。",

        "reviews": "评价",
        "reviews_title": "旅行者的\n评价。",
        "reviews_text": (
            "来自探索过曼吉斯套的游客的真实体验。"
        ),

        "map_title": "在地图上\n探索曼吉斯套。",
        "map_text": (
            "在一张地图上探索曼吉斯套最著名的自然景观。"
        ),

        "tour_duration_label": "行程时间",
        "tour_transport": "交通",
        "tour_group": "团队",
        "tour_region": "地区",
        "one_day": "ONE DAY",

        "routes_title": "一日线路",

        "route_1": "伊贝克提赛 — 图兹拜尔",
        "route_2": "托雷什 — 图兹拜尔",
        "route_2_note": "下雨天气不前往图兹拜尔下部。",

        "route_3": (
            "卡帕姆赛 — 沙克帕克阿塔 — "
            "托雷什 — 科卡拉 — 舍尔卡拉 — 艾拉克特"
        ),

        "route_4": (
            "伊贝克提赛 — 克孜勒库普 — 博兹日拉"
        ),

        "route_5": (
            "克孜勒库普 — 博克特 — 博兹日拉"
        ),

        "route_5_note": "下雨天气不前往博克特。",

        "tour_price_note": "价格取决于所选择的路线。",

        "tour_includes": "费用包含",
        "include_4x4": "4×4越野车",
        "include_guide": "当地向导",
        "include_support": "全程路线陪同",
        "include_water": "饮用水",

        "tour_2day_title": "2天JEEP越野探险",

        "tour_2day_description": (
            "穿越曼吉斯套最具代表性的自然景观，"
            "体验越野探险、舒适旅程、安全保障和难忘的风景。"
        ),

        "price": "价格",
        "per_tour": "每团",
        "duration": "行程时间",
        "vehicle": "交通工具",
        "start_end": "开始 / 结束",
        "distance": "距离",
        "itinerary": "行程路线",
        "day": "天",
        "meals": "餐食",
        "stay": "住宿",

        "day1_route": (
            "阿克套 • 卡拉姆赛 • 沙克帕克阿塔 • 托雷什 • "
            "科卡拉 • 舍尔卡拉 • 艾拉克特"
        ),

        "day1_text": (
            "在您的酒店或阿克套机场与导游会合。"
            "第一站前往卡拉姆赛峡谷，随后参观沙克帕克阿塔地下清真寺，"
            "这座清真寺开凿于里海海岸上方的白垩悬崖之中。"
            "接着前往托雷什山谷，这里以数千个巨大的圆形石质结核而闻名，"
            "其中一些直径可达4米。随后前往舍尔卡拉山短暂停留拍照，"
            "再沿着土路前往艾拉克特城堡谷。"
        ),

        "day1_meals": "简单零食、现场晚餐",
        "day1_stay": "星空下的帐篷",

        "day2_route": (
            "博兹日拉 • 博克特 • 克孜勒库普"
        ),

        "day2_text": (
            "早晨前往博兹日拉地区，欣赏由古代特提斯海洋遗迹形成的"
            "壮丽全景。请关注天气并携带保暖衣物，因为这里的气候"
            "可能与阿克套相差10–15°C。随后参观博克特山，"
            "这是一座独立矗立在草原上的条纹金字塔形山峰。"
            "之后前往附近的克孜勒库普地区，白垩和铁矿形成的"
            "彩色岩层构成令人惊叹的景观。"
            "当天结束后返回阿克套。"
        ),

        "day2_meals": "早餐、简单午餐",
        "day2_stay": "阿克套，晚上",

        "what_included": "费用包含",
        "additional": "其他服务",

        "include_transfer": "4×4越野车接送",
        "include_experienced_guide": "经验丰富的导游",
        "include_entrance": "所有门票",
        "include_snacks": "零食和饮料",
        "include_tents": "帐篷",
        "include_sleeping": "睡袋和睡垫",
        "include_lighting": "营地照明",
        "include_camping": "露营设备",
        "include_refrigerator": "冰箱",
        "include_drone": "无人机拍摄",
        "include_photo": "摄影支持",

        "additional_guide": "英语导游",
        "on_request": "根据要求",
    },
}


# =========================================================
# ADDITIONAL LANGUAGES
# =========================================================

# Each language inherits any untranslated text from English,
# so all site sections remain visible while using local labels.
TRANSLATIONS["it"] = dict(
    TRANSLATIONS["en"],
    tours="Tour", about="Chi siamo", gallery="Galleria",
    booking="Prenotazione", book="Prenota", reserve="Prenota",
    reviews="Recensioni", name="Il tuo nome", phone="Telefono / WhatsApp",
    tour_select="Scegli un tour", route_select="Scegli un itinerario",
    guests="Numero di ospiti", comment="Commento", send="Invia richiesta",
    price="Prezzo", per_tour="per tour", duration="Durata",
    itinerary="Itinerario", back="Indietro",
)

TRANSLATIONS["fr"] = dict(
    TRANSLATIONS["en"],
    tours="Circuits", about="À propos", gallery="Galerie",
    booking="Réservation", book="Réserver", reserve="Réserver",
    reviews="Avis", name="Votre nom", phone="Téléphone / WhatsApp",
    tour_select="Choisissez un circuit", route_select="Choisissez un itinéraire",
    guests="Nombre de voyageurs", comment="Commentaire", send="Envoyer la demande",
    price="Prix", per_tour="par circuit", duration="Durée",
    itinerary="Itinéraire", back="Retour",
)

TRANSLATIONS["pl"] = dict(
    TRANSLATIONS["en"],
    tours="Wycieczki", about="O nas", gallery="Galeria",
    booking="Rezerwacja", book="Zarezerwuj", reserve="Zarezerwuj",
    reviews="Opinie", name="Twoje imię", phone="Telefon / WhatsApp",
    tour_select="Wybierz wycieczkę", route_select="Wybierz trasę",
    guests="Liczba gości", comment="Komentarz", send="Wyślij zgłoszenie",
    price="Cena", per_tour="za wycieczkę", duration="Czas trwania",
    itinerary="Trasa", back="Wstecz",
)

TRANSLATIONS["ja"] = dict(
    TRANSLATIONS["en"],
    tours="ツアー", about="私たちについて", gallery="ギャラリー",
    booking="予約", book="予約する", reserve="予約する",
    reviews="レビュー", name="お名前", phone="電話 / WhatsApp",
    tour_select="ツアーを選択", route_select="ルートを選択",
    guests="参加人数", comment="コメント", send="送信する",
    price="料金", per_tour="ツアーあたり", duration="所要時間",
    itinerary="旅程", back="戻る",
)

# Full landing-page copy for the additional languages.
TRANSLATIONS["it"].update({
    "hero_eyebrow": "NATURA SELVAGGIA • MANGYSTAU",
    "hero_explore": "Esplora i tour", "hero_gallery": "Guarda la galleria",
    "popular": "ITINERARI POPOLARI", "choose": "Scegli la tua\navventura.",
    "discover": "Scopri luoghi indimenticabili: canyon desertici, montagne, altopiani e il Mar Caspio.",
    "discover_title": "SCOPRI IL MANGYSTAU",
    "discover_text": "Esplora la natura selvaggia del Mangystau, dalle leggendarie scogliere di Bozzhyra ai deserti infiniti e alla costa del Mar Caspio.",
    "why": "PERCHÉ MANGYSTAU TOUR", "benefit_1_title": "Affidabili 4×4",
    "benefit_1_text": "Comodi fuoristrada preparati per gli itinerari.",
    "benefit_2_title": "Guide locali", "benefit_2_text": "Guide esperte che conoscono ogni angolo del Mangystau.",
    "benefit_3_title": "Comfort", "benefit_3_text": "Tutto il necessario per un viaggio senza pensieri.",
    "benefit_4_title": "Sicurezza", "benefit_4_text": "Itinerari verificati e assistenza attenta.",
    "moments_title": "Momenti\nindimenticabili.", "moments_text": "Qui ogni chilometro sembra una scena di un film.",
    "ready": "PRONTO PER IL VIAGGIO?", "time": "È il momento di scoprire\nil Mangystau.",
    "booking_text": "Lascia una richiesta: il nostro manager ti contatterà e ti aiuterà a scegliere l'itinerario.",
    "name_placeholder": "Inserisci il tuo nome", "comment_placeholder": "Raccontaci il tuo viaggio...",
    "wild_nature": "Natura selvaggia. Emozioni autentiche.", "reviews_title": "Recensioni dei\nviaggiatori.",
    "reviews_text": "Le impressioni degli ospiti che hanno già visitato il Mangystau.",
    "map_title": "SCOPRI IL MANGYSTAU\nSULLA MAPPA.", "map_text": "Esplora i luoghi naturali più famosi del Mangystau su un'unica mappa.",
})

TRANSLATIONS["fr"].update({
    "hero_eyebrow": "NATURE SAUVAGE • MANGYSTAU",
    "hero_explore": "Explorer les circuits", "hero_gallery": "Voir la galerie",
    "popular": "ITINÉRAIRES POPULAIRES", "choose": "Choisissez votre\naventure.",
    "discover": "Découvrez des lieux inoubliables : canyons désertiques, montagnes, plateaux et mer Caspienne.",
    "discover_title": "DÉCOUVREZ LE MANGYSTAU",
    "discover_text": "Explorez la nature sauvage du Mangystau, des falaises légendaires de Bozzhyra aux déserts infinis et à la côte de la mer Caspienne.",
    "why": "POURQUOI MANGYSTAU TOUR", "benefit_1_title": "4×4 fiables",
    "benefit_1_text": "Des véhicules tout-terrain confortables, préparés pour les itinéraires.",
    "benefit_2_title": "Guides locaux", "benefit_2_text": "Des guides expérimentés qui connaissent chaque recoin du Mangystau.",
    "benefit_3_title": "Confort", "benefit_3_text": "Tout le nécessaire pour voyager sans souci.",
    "benefit_4_title": "Sécurité", "benefit_4_text": "Des itinéraires vérifiés et un accompagnement attentif.",
    "moments_title": "Des moments\ninoubliables.", "moments_text": "Ici, chaque kilomètre ressemble à une scène de film.",
    "ready": "PRÊT À PARTIR ?", "time": "Il est temps de découvrir\nle Mangystau.",
    "booking_text": "Laissez une demande. Notre responsable vous contactera et vous aidera à choisir votre itinéraire.",
    "name_placeholder": "Entrez votre nom", "comment_placeholder": "Parlez-nous de votre voyage...",
    "wild_nature": "Nature sauvage. Émotions authentiques.", "reviews_title": "Avis des\nvoyageurs.",
    "reviews_text": "Les impressions des visiteurs qui ont déjà découvert le Mangystau.",
    "map_title": "DÉCOUVREZ LE MANGYSTAU\nSUR LA CARTE.", "map_text": "Explorez les sites naturels les plus célèbres du Mangystau sur une seule carte.",
})

TRANSLATIONS["pl"].update({
    "hero_eyebrow": "DZIKA PRZYRODA • MANGYSTAU",
    "hero_explore": "Odkryj wycieczki", "hero_gallery": "Zobacz galerię",
    "popular": "POPULARNE TRASY", "choose": "Wybierz swoją\nprzygodę.",
    "discover": "Odkryj niezapomniane miejsca: pustynne kaniony, góry, płaskowyże i Morze Kaspijskie.",
    "discover_title": "ODKRYJ MANGYSTAU",
    "discover_text": "Poznaj dziką przyrodę Mangystau — od legendarnych klifów Bozzhyry po bezkresne pustynie i wybrzeże Morza Kaspijskiego.",
    "why": "DLACZEGO MANGYSTAU TOUR", "benefit_1_title": "Niezawodne 4×4",
    "benefit_1_text": "Wygodne samochody terenowe przygotowane na każdą trasę.",
    "benefit_2_title": "Lokalni przewodnicy", "benefit_2_text": "Doświadczeni przewodnicy znający każdy zakątek Mangystau.",
    "benefit_3_title": "Komfort", "benefit_3_text": "Wszystko, czego potrzeba do beztroskiej podróży.",
    "benefit_4_title": "Bezpieczeństwo", "benefit_4_text": "Sprawdzone trasy i uważna opieka.",
    "moments_title": "Chwile,\nktóre zostają.", "moments_text": "Tutaj każdy kilometr wygląda jak kadr z filmu.",
    "ready": "GOTOWY NA PODRÓŻ?", "time": "Czas odkryć\nMangystau.",
    "booking_text": "Zostaw zgłoszenie. Nasz menedżer skontaktuje się z Tobą i pomoże wybrać trasę.",
    "name_placeholder": "Wpisz swoje imię", "comment_placeholder": "Opowiedz nam o swojej podróży...",
    "wild_nature": "Dzika przyroda. Prawdziwe emocje.", "reviews_title": "Opinie\npodróżników.",
    "reviews_text": "Wrażenia gości, którzy już odwiedzili Mangystau.",
    "map_title": "ODKRYJ MANGYSTAU\nNA MAPIE.", "map_text": "Odkryj na jednej mapie najpopularniejsze miejsca przyrodnicze Mangystau.",
})

TRANSLATIONS["ja"].update({
    "hero_eyebrow": "大自然 • マンギスタウ", "hero_explore": "ツアーを見る", "hero_gallery": "ギャラリーを見る",
    "popular": "人気のルート", "choose": "あなただけの\n冒険を選ぼう。",
    "discover": "砂漠の峡谷、山々、高原、カスピ海など、忘れられない場所を発見しましょう。",
    "discover_title": "マンギスタウを発見する", "discover_text": "伝説的なボズジラの断崖から果てしない砂漠、カスピ海沿岸まで、マンギスタウの大自然を探索しましょう。",
    "why": "MANGYSTAU TOURを選ぶ理由", "benefit_1_title": "信頼できる4×4",
    "benefit_1_text": "ルートに対応した快適な四輪駆動車。", "benefit_2_title": "現地ガイド",
    "benefit_2_text": "マンギスタウの隅々まで知る経験豊富なガイド。", "benefit_3_title": "快適さ",
    "benefit_3_text": "安心して旅を楽しむために必要なものを用意しています。", "benefit_4_title": "安全",
    "benefit_4_text": "確認済みのルートと丁寧なサポート。", "moments_title": "忘れられない\n瞬間。",
    "moments_text": "ここでは、すべての一キロが映画のワンシーンのようです。", "ready": "旅の準備はできましたか？",
    "time": "マンギスタウを発見する\n時間です。", "booking_text": "お申し込みください。担当者が連絡し、最適なルート選びをお手伝いします。",
    "name_placeholder": "お名前を入力", "comment_placeholder": "旅について教えてください...", "wild_nature": "大自然。本物の感動。",
    "reviews_title": "旅行者の\nレビュー。", "reviews_text": "マンギスタウを訪れたゲストの感想。",
    "map_title": "地図で\nマンギスタウを発見。", "map_text": "マンギスタウを代表する自然スポットを一つの地図で探索できます。",
})

# ===========================================================================
# ТОЛЫҚ АУДАРМА: IT / FR / PL / JA
# ---------------------------------------------------------------------------
# Бұрын бұл төрт тіл негізінен ағылшыншаға түсіп тұрған. Енді барлық
# интерфейс мәтіні аударылды.
#
# Жер атаулары (Бозжыра, Шеркала, Айрақты) аударылмайды — олар
# барлық тілде сол күйінде жазылады.
# ===========================================================================

TRANSLATIONS["it"].update({
    # --- жалпы ---
    "benefit_3_title": "Comfort",
    "moments_label": "MANGYSTAU",
    "tour_duration_label": "Durata",
    "tour_transport": "Trasporto",
    "tour_group": "Gruppo",
    "tour_region": "Regione",
    "one_day": "UN GIORNO",
    "routes_title": "Itinerari di un giorno",
    "route_1": "Ybykty-Sai — Tuzbair",
    "route_2": "Torysh — Tuzbair",
    "route_2_note": "Con la pioggia non scendiamo nella parte bassa di Tuzbair.",
    "route_3": "Kapamsai — Shakpak-Ata — Torysh — Kokala — Sherkala — Airakty",
    "route_4": "Ybykty-Sai — Kyzylkup — Bozzhyra",
    "route_5": "Kyzylkup — Bokty — Bozzhyra",
    "route_5_note": "Con la pioggia non si visita Bokty.",
    "tour_price_note": "Il prezzo dipende dall'itinerario scelto.",
    "tour_includes": "Il tour comprende",
    "include_4x4": "Fuoristrada 4×4",
    "include_guide": "Guida locale",
    "include_support": "Assistenza lungo il percorso",
    "include_water": "Acqua potabile",
    "tour_2day_title": "SPEDIZIONE IN JEEP DI 2 GIORNI",
    "tour_2day_description": "Avventura fuoristrada tra i paesaggi più iconici del Mangystau: comfort, sicurezza e panorami indimenticabili.",
    "per_tour": "per tour",
    "vehicle": "VEICOLO",
    "start_end": "INIZIO / FINE",
    "day": "GIORNO",
    "meals": "PASTI",
    "stay": "PERNOTTAMENTO",
    "day1_route": "AKTAU • KARAMSAI • SHAKPAK-ATA • TORYSH • KOKALA • SHERKALA • AIRAKTY",
    "day1_text": "Incontro con la guida in hotel o all'aeroporto di Aktau. Prima sosta al canyon di Karamsai, poi la moschea sotterranea di Shakpak-Ata scavata nella roccia calcarea sopra la costa del Caspio. Si prosegue verso la valle di Torysh, famosa per le migliaia di concrezioni di pietra rotonde fino a 4 metri di diametro. Sosta fotografica al monte Sherkala e infine, lungo una pista sterrata, la Valle dei Castelli di Airakty.",
    "day1_meals": "Spuntino leggero, cena sul posto",
    "day1_stay": "Tenda sotto le stelle",
    "day2_route": "BOZZHYRA • BOKTY • KYZYLKUP",
    "day2_text": "Al mattino si parte per Bozzhyra, con panorami straordinari formati dai resti dell'antico oceano Tetide. Conviene portare indumenti caldi: il clima può differire di 10–15 °C rispetto ad Aktau. Poi il monte Bokty, una piramide striata che si erge solitaria sulla steppa, e il vicino Kyzylkup, dove strati colorati di gesso e ferro creano un paesaggio unico. Rientro ad Aktau in serata.",
    "day2_meals": "Colazione, pranzo leggero",
    "day2_stay": "Aktau, sera",
    "what_included": "COSA È INCLUSO",
    "additional": "SUPPLEMENTI",
    "include_transfer": "Transfer 4×4",
    "include_experienced_guide": "Guida esperta",
    "include_entrance": "Tutti i biglietti d'ingresso",
    "include_snacks": "Snack e bevande",
    "include_tents": "Tende",
    "include_sleeping": "Sacchi a pelo e materassini",
    "include_lighting": "Illuminazione del campo",
    "include_camping": "Attrezzatura da campeggio",
    "include_refrigerator": "Frigorifero",
    "include_drone": "Riprese con drone",
    "include_photo": "Servizio fotografico",
    "additional_guide": "Guida di lingua inglese",
    "on_request": "su richiesta",

    # --- навигация мен интерфейс ---
    "back_to_site": "Torna al sito",
    "menu": "Menu",
    "language": "Lingua",
    "close": "Chiudi",
    "skip": "Vai al contenuto",
    "email": "Email",
    "phone_placeholder": "700 000 00 00",
    "country_code": "Prefisso",
    "tour_date": "Data del tour",
    "guests_note": "Fino a 3 ospiti per gruppo. Dal 4º ospite si applica un supplemento.",
    "total_price": "Totale",
    "required_note": "I campi con * sono obbligatori.",
    "price_from": "A partire da",
    "price_on_request": "Prezzo su richiesta",
    "tour_label": "Tour",
    "view_tour": "Vedi il tour",
    "map_label": "Mappa",
    "route": "Percorso",
    "routes": "Percorsi",
    "days": "Giorni",
    "stop": "Tappa",
    "discover_mangystau": "Scopri il Mangystau",

    # --- пакеттер ---
    "package": "Pacchetto",
    "packages": "Pacchetti",
    "packages_title": "Scegli il pacchetto",
    "packages_text": "Stesso itinerario, diverso livello di comfort e di riprese.",
    "package_includes": "Include",
    "most_popular": "Il più scelto",
    "select_package": "Scegli",

    # --- брондау ---
    "booking_kicker": "Prenotazione",
    "booking_hero_lead": "Il tuo",
    "booking_hero_accent": "viaggio",
    "booking_hero_tail": "inizia qui",
    "booking_hero_text": "Scegli l'itinerario e prenota la tua esperienza privata nel Mangystau.",
    "private_tour": "Tour privato",
    "guests_1_3": "1–3 ospiti",
    "one_fixed_price": "Prezzo unico",
    "book_your_tour": "Prenota il tuo tour",
    "form_intro": "Compila i dati e scegli il percorso.",

    # --- хабарламалар ---
    "msg_ok": "Grazie! Abbiamo ricevuto la richiesta e ti contatteremo a breve.",
    "msg_name": "Inserisci il tuo nome.",
    "msg_phone": "Inserisci il numero di telefono.",
    "msg_email": "Inserisci un indirizzo email valido.",
    "msg_date": "Scegli la data del tour.",
    "msg_date_format": "Formato data non valido.",
    "msg_date_past": "Scegli una data futura.",
    "msg_date_far": "Scegli una data entro i prossimi 18 mesi.",
    "msg_tour": "Seleziona un tour dall'elenco.",
    "msg_package": "Seleziona un pacchetto.",
    "msg_guests": "Il numero di ospiti deve essere tra 1 e {max}.",
    "msg_groups": "Il numero di gruppi deve essere tra 1 e {max}.",
    "msg_route": "Scegli un percorso per questo tour.",

    # --- топтар мен қызметтер ---
    "group_note": "Un gruppo comprende fino a 3 ospiti. Dal 4º ospite si applica un supplemento in base alla durata del tour.",
    "groups": "Gruppi",
    "extra_guest_fee": "Supplemento ospite",
    "extra_guests": "Ospiti aggiuntivi",
    "extra_services": "Servizi extra",
    "extra_services_text": "Facoltativi, si aggiungono al totale. I servizi giornalieri si contano per ogni giorno del tour.",
    "services_price": "Servizi extra",
    "once": "una tantum",
    "per_day": "al giorno",
    "per_person": "a persona",
    "base_price": "Tour e pacchetto",
    "groups_label": "Numero di gruppi",
    "groups_note": "Un gruppo = un veicolo, fino a 3 ospiti. Un secondo gruppo raddoppia il prezzo.",
    "group_word": "gruppo",
    "groups_word": "gruppi",
    "up_to_guests": "fino a {n} ospiti",
    "guests_label": "Numero di ospiti",
    "guests_hint": "Fino a 3 per veicolo",

    # --- маршрут ---
    "distance_note": "circa",
    "rain_short": "Chiuso con la pioggia",
    "dress_short": "Abbigliamento coprente",
    "choose_route": "Scegli il percorso",
    "choose_route_text": "Un giorno, un percorso. Scegli quello che preferisci.",
    "route_label": "Percorso",
    "select_route": "Scegli il percorso",
    "book_this_route": "Prenota questo percorso",
    "rain_title": "Pioggia e forza maggiore",
    "rain_text": "Con la pioggia alcuni luoghi sono chiusi per sicurezza: Tuzbair, il monte Bokty e la parte bassa di Bozzhyra. La guida propone un'alternativa nello stesso giorno.",
    "dress_title": "Visita alle moschee",
    "dress_text": "Shakpak-Ata e Karaman-Ata sono moschee sotterranee ancora in uso. Si richiede abbigliamento coprente: spalle e ginocchia coperte. Per le donne è consigliato un foulard.",

    # --- шолу ---
    "overview": "Il tour in breve",
    "overview_text": "Tutto quello che serve sapere prima di partire.",
    "included_title": "Cosa è incluso",
    "extras_title": "Disponibile a pagamento",
    "start_point": "Aktau — hotel o aeroporto",
    "group_size": "1–3 ospiti per veicolo",
    "vehicle_type": "4×4 attrezzato",

    # --- қорытынды карточка ---
    "confirm_24h": "Conferma entro 24 ore",
    "pay_after": "Pagamento dopo la conferma",
    "tour_price_label": "Prezzo del tour",
    "your_booking": "La tua prenotazione",
    "pick_tour_first": "Scegli un tour per vedere i dettagli.",
    "summary_package": "Pacchetto",
    "summary_route": "Percorso",
    "summary_groups": "Gruppi",
    "summary_date": "Data",
    "summary_total": "Totale",
    "contacts_step": "Contatti",
    "trip_step": "Il tuo viaggio",
    "not_selected": "Non selezionato",
    "select_tour_hint": "Scegli dall'elenco",
    "sending": "Invio",
    "sent": "Richiesta inviata",

    # --- валюта мен карта ---
    "currency_note": "Indicativo, al cambio attuale",
    "currency": "Valuta",
    "all_points": "Tutti i luoghi",
    "map_filter": "Mostra il percorso di",
})


TRANSLATIONS["fr"].update({
    "benefit_3_title": "Confort",
    "moments_label": "MANGYSTAU",
    "tour_duration_label": "Durée",
    "tour_transport": "Transport",
    "tour_group": "Groupe",
    "tour_region": "Région",
    "one_day": "UN JOUR",
    "routes_title": "Itinéraires d'une journée",
    "route_1": "Ybykty-Saï — Touzbaïr",
    "route_2": "Torych — Touzbaïr",
    "route_2_note": "Par temps de pluie, nous ne descendons pas dans la partie basse de Touzbaïr.",
    "route_3": "Kapamsaï — Chakpak-Ata — Torych — Kokala — Cherkala — Aïrakty",
    "route_4": "Ybykty-Saï — Kyzylkoup — Bozzhyra",
    "route_5": "Kyzylkoup — Bokty — Bozzhyra",
    "route_5_note": "Par temps de pluie, Bokty n'est pas visité.",
    "tour_price_note": "Le prix dépend de l'itinéraire choisi.",
    "tour_includes": "Le circuit comprend",
    "include_4x4": "Véhicule tout-terrain 4×4",
    "include_guide": "Guide local",
    "include_support": "Accompagnement sur tout le parcours",
    "include_water": "Eau potable",
    "tour_2day_title": "EXPÉDITION EN JEEP DE 2 JOURS",
    "tour_2day_description": "Aventure tout-terrain à travers les paysages les plus emblématiques du Mangystau : confort, sécurité et panoramas inoubliables.",
    "per_tour": "par circuit",
    "vehicle": "VÉHICULE",
    "start_end": "DÉBUT / FIN",
    "day": "JOUR",
    "meals": "REPAS",
    "stay": "HÉBERGEMENT",
    "day1_route": "AKTAU • KARAMSAÏ • CHAKPAK-ATA • TORYCH • KOKALA • CHERKALA • AÏRAKTY",
    "day1_text": "Rencontre avec votre guide à l'hôtel ou à l'aéroport d'Aktau. Premier arrêt au canyon de Karamsaï, puis la mosquée souterraine de Chakpak-Ata creusée dans la falaise crayeuse au-dessus de la mer Caspienne. Direction la vallée de Torych, célèbre pour ses milliers de concrétions rocheuses rondes atteignant 4 mètres de diamètre. Arrêt photo au mont Cherkala, puis route de terre jusqu'à la vallée des Châteaux d'Aïrakty.",
    "day1_meals": "Collation, dîner sur place",
    "day1_stay": "Tente sous les étoiles",
    "day2_route": "BOZZHYRA • BOKTY • KYZYLKOUP",
    "day2_text": "Le matin, cap sur Bozzhyra et ses panoramas façonnés par les vestiges de l'ancien océan Téthys. Prévoyez des vêtements chauds : la température peut différer de 10 à 15 °C par rapport à Aktau. Ensuite, le mont Bokty, pyramide rayée dressée seule au-dessus de la steppe, puis Kyzylkoup, où les couches colorées de craie et de fer créent un paysage saisissant. Retour à Aktau en fin de journée.",
    "day2_meals": "Petit-déjeuner, déjeuner léger",
    "day2_stay": "Aktau, en soirée",
    "what_included": "CE QUI EST INCLUS",
    "additional": "EN SUPPLÉMENT",
    "include_transfer": "Transfert 4×4",
    "include_experienced_guide": "Guide expérimenté",
    "include_entrance": "Tous les droits d'entrée",
    "include_snacks": "En-cas et boissons",
    "include_tents": "Tentes",
    "include_sleeping": "Sacs de couchage et matelas",
    "include_lighting": "Éclairage du campement",
    "include_camping": "Matériel de camping",
    "include_refrigerator": "Réfrigérateur",
    "include_drone": "Prises de vue par drone",
    "include_photo": "Accompagnement photo",
    "additional_guide": "Guide anglophone",
    "on_request": "sur demande",

    "back_to_site": "Retour au site",
    "menu": "Menu",
    "language": "Langue",
    "close": "Fermer",
    "skip": "Aller au contenu",
    "email": "E-mail",
    "phone_placeholder": "700 000 00 00",
    "country_code": "Indicatif",
    "tour_date": "Date du circuit",
    "guests_note": "Jusqu'à 3 voyageurs par groupe. À partir du 4e, un supplément s'applique.",
    "total_price": "Total",
    "required_note": "Les champs marqués d'un * sont obligatoires.",
    "price_from": "À partir de",
    "price_on_request": "Prix sur demande",
    "tour_label": "Circuit",
    "view_tour": "Voir le circuit",
    "map_label": "Carte",
    "route": "Étape",
    "routes": "Étapes",
    "days": "Jours",
    "stop": "Arrêt",
    "discover_mangystau": "Découvrez le Mangystau",

    "package": "Formule",
    "packages": "Formules",
    "packages_title": "Choisissez votre formule",
    "packages_text": "Même itinéraire, niveau de confort et de prise de vue différent.",
    "package_includes": "Comprend",
    "most_popular": "Le plus choisi",
    "select_package": "Choisir",

    "booking_kicker": "Réservation",
    "booking_hero_lead": "Votre",
    "booking_hero_accent": "voyage",
    "booking_hero_tail": "commence ici",
    "booking_hero_text": "Choisissez votre itinéraire et réservez votre circuit privé au Mangystau.",
    "private_tour": "Circuit privé",
    "guests_1_3": "1–3 voyageurs",
    "one_fixed_price": "Prix unique",
    "book_your_tour": "Réservez votre circuit",
    "form_intro": "Remplissez vos informations et choisissez l'itinéraire.",

    "msg_ok": "Merci ! Nous avons bien reçu votre demande et vous recontacterons rapidement.",
    "msg_name": "Veuillez indiquer votre nom.",
    "msg_phone": "Veuillez indiquer votre numéro de téléphone.",
    "msg_email": "Veuillez saisir une adresse e-mail valide.",
    "msg_date": "Veuillez choisir la date du circuit.",
    "msg_date_format": "Format de date invalide.",
    "msg_date_past": "Veuillez choisir une date future.",
    "msg_date_far": "Veuillez choisir une date dans les 18 prochains mois.",
    "msg_tour": "Veuillez sélectionner un circuit dans la liste.",
    "msg_package": "Veuillez sélectionner une formule.",
    "msg_guests": "Le nombre de voyageurs doit être entre 1 et {max}.",
    "msg_groups": "Le nombre de groupes doit être entre 1 et {max}.",
    "msg_route": "Veuillez choisir un itinéraire pour ce circuit.",

    "group_note": "Un groupe compte jusqu'à 3 voyageurs. À partir du 4e, un supplément s'applique selon la durée du circuit.",
    "groups": "Groupes",
    "extra_guest_fee": "Supplément voyageur",
    "extra_guests": "Voyageurs supplémentaires",
    "extra_services": "Services supplémentaires",
    "extra_services_text": "Facultatifs, ajoutés au total. Les services journaliers sont comptés pour chaque jour du circuit.",
    "services_price": "Services supplémentaires",
    "once": "une fois",
    "per_day": "par jour",
    "per_person": "par personne",
    "base_price": "Circuit et formule",
    "groups_label": "Nombre de groupes",
    "groups_note": "Un groupe = un véhicule, jusqu'à 3 voyageurs. Un second groupe double le prix.",
    "group_word": "groupe",
    "groups_word": "groupes",
    "up_to_guests": "jusqu'à {n} voyageurs",
    "guests_label": "Nombre de voyageurs",
    "guests_hint": "Jusqu'à 3 par véhicule",

    "distance_note": "environ",
    "rain_short": "Fermé par temps de pluie",
    "dress_short": "Tenue couvrante exigée",
    "choose_route": "Choisissez votre itinéraire",
    "choose_route_text": "Un jour, un itinéraire. Choisissez celui qui vous plaît.",
    "route_label": "Itinéraire",
    "select_route": "Choisir l'itinéraire",
    "book_this_route": "Réserver cet itinéraire",
    "rain_title": "Pluie et force majeure",
    "rain_text": "Par temps de pluie, certains sites sont fermés pour des raisons de sécurité : Touzbaïr, le mont Bokty et la partie basse de Bozzhyra. Le guide propose alors une alternative le jour même.",
    "dress_title": "Visite des mosquées",
    "dress_text": "Chakpak-Ata et Karaman-Ata sont des mosquées souterraines toujours en activité. Une tenue couvrante est demandée : épaules et genoux couverts. Un foulard est recommandé pour les femmes.",

    "overview": "Aperçu du circuit",
    "overview_text": "Tout ce qu'il faut savoir avant le départ.",
    "included_title": "Ce qui est inclus",
    "extras_title": "Disponible en supplément",
    "start_point": "Aktau — hôtel ou aéroport",
    "group_size": "1–3 voyageurs par véhicule",
    "vehicle_type": "4×4 préparé",

    "confirm_24h": "Confirmation sous 24 heures",
    "pay_after": "Paiement après confirmation",
    "tour_price_label": "Prix du circuit",
    "your_booking": "Votre réservation",
    "pick_tour_first": "Choisissez un circuit pour voir les détails.",
    "summary_package": "Formule",
    "summary_route": "Itinéraire",
    "summary_groups": "Groupes",
    "summary_date": "Date",
    "summary_total": "Total",
    "contacts_step": "Coordonnées",
    "trip_step": "Votre voyage",
    "not_selected": "Non sélectionné",
    "select_tour_hint": "Choisir dans la liste",
    "sending": "Envoi",
    "sent": "Demande envoyée",

    "currency_note": "Approximatif, au taux actuel",
    "currency": "Devise",
    "all_points": "Tous les lieux",
    "map_filter": "Afficher l'itinéraire de",
})


TRANSLATIONS["pl"].update({
    "benefit_3_title": "Komfort",
    "moments_label": "MANGYSTAU",
    "tour_duration_label": "Czas trwania",
    "tour_transport": "Transport",
    "tour_group": "Grupa",
    "tour_region": "Region",
    "one_day": "JEDEN DZIEŃ",
    "routes_title": "Trasy jednodniowe",
    "route_1": "Ybykty-Saj — Tuzbair",
    "route_2": "Torysz — Tuzbair",
    "route_2_note": "Przy deszczowej pogodzie nie zjeżdżamy do dolnej części Tuzbairu.",
    "route_3": "Kapamsaj — Szakpak-Ata — Torysz — Kokala — Szerkala — Airakty",
    "route_4": "Ybykty-Saj — Kyzyłkup — Bozzhyra",
    "route_5": "Kyzyłkup — Bokty — Bozzhyra",
    "route_5_note": "Przy deszczowej pogodzie nie odwiedzamy Bokty.",
    "tour_price_note": "Cena zależy od wybranej trasy.",
    "tour_includes": "Wycieczka obejmuje",
    "include_4x4": "Samochód terenowy 4×4",
    "include_guide": "Lokalny przewodnik",
    "include_support": "Opieka na całej trasie",
    "include_water": "Woda pitna",
    "tour_2day_title": "2-DNIOWA WYPRAWA JEEPEM",
    "tour_2day_description": "Terenowa przygoda przez najbardziej charakterystyczne krajobrazy Mangystau — komfort, bezpieczeństwo i niezapomniane widoki.",
    "per_tour": "za wycieczkę",
    "vehicle": "POJAZD",
    "start_end": "START / META",
    "day": "DZIEŃ",
    "meals": "WYŻYWIENIE",
    "stay": "NOCLEG",
    "day1_route": "AKTAU • KARAMSAJ • SZAKPAK-ATA • TORYSZ • KOKALA • SZERKALA • AIRAKTY",
    "day1_text": "Spotkanie z przewodnikiem w hotelu lub na lotnisku w Aktau. Pierwszy przystanek w kanionie Karamsaj, następnie podziemny meczet Szakpak-Ata wykuty w kredowej skale nad brzegiem Morza Kaspijskiego. Dalej dolina Torysz, słynąca z tysięcy okrągłych konkrecji o średnicy do 4 metrów. Krótki postój na zdjęcia pod górą Szerkala, a na koniec droga gruntowa do Doliny Zamków Airakty.",
    "day1_meals": "Lekka przekąska, kolacja na miejscu",
    "day1_stay": "Namiot pod gwiazdami",
    "day2_route": "BOZZHYRA • BOKTY • KYZYŁKUP",
    "day2_text": "Rano wyruszamy do Bozzhyry, gdzie rozciągają się panoramy uformowane przez pozostałości dawnego oceanu Tetydy. Warto zabrać ciepłe ubranie — temperatura potrafi różnić się o 10–15 °C od Aktau. Następnie góra Bokty, pasiasta piramida wznosząca się samotnie nad stepem, oraz pobliski Kyzyłkup, gdzie kolorowe warstwy kredy i żelaza tworzą niezwykły krajobraz. Wieczorem powrót do Aktau.",
    "day2_meals": "Śniadanie, lekki obiad",
    "day2_stay": "Aktau, wieczorem",
    "what_included": "CO JEST WLICZONE",
    "additional": "DODATKOWO",
    "include_transfer": "Transfer 4×4",
    "include_experienced_guide": "Doświadczony przewodnik",
    "include_entrance": "Wszystkie bilety wstępu",
    "include_snacks": "Przekąski i napoje",
    "include_tents": "Namioty",
    "include_sleeping": "Śpiwory i maty",
    "include_lighting": "Oświetlenie obozu",
    "include_camping": "Sprzęt kempingowy",
    "include_refrigerator": "Lodówka",
    "include_drone": "Ujęcia z drona",
    "include_photo": "Obsługa fotograficzna",
    "additional_guide": "Przewodnik anglojęzyczny",
    "on_request": "na życzenie",

    "back_to_site": "Powrót na stronę",
    "menu": "Menu",
    "language": "Język",
    "close": "Zamknij",
    "skip": "Przejdź do treści",
    "email": "E-mail",
    "phone_placeholder": "700 000 00 00",
    "country_code": "Numer kierunkowy",
    "tour_date": "Data wyjazdu",
    "guests_note": "Do 3 gości w grupie. Od 4. gościa doliczana jest dopłata.",
    "total_price": "Razem",
    "required_note": "Pola oznaczone * są obowiązkowe.",
    "price_from": "Cena od",
    "price_on_request": "Cena na życzenie",
    "tour_label": "Wycieczka",
    "view_tour": "Zobacz wycieczkę",
    "map_label": "Mapa",
    "route": "Trasa",
    "routes": "Trasy",
    "days": "Dni",
    "stop": "Przystanek",
    "discover_mangystau": "Odkryj Mangystau",

    "package": "Pakiet",
    "packages": "Pakiety",
    "packages_title": "Wybierz pakiet",
    "packages_text": "Ta sama trasa, inny poziom komfortu i materiałów zdjęciowych.",
    "package_includes": "Zawiera",
    "most_popular": "Najczęściej wybierany",
    "select_package": "Wybierz",

    "booking_kicker": "Rezerwacja",
    "booking_hero_lead": "Twoja",
    "booking_hero_accent": "podróż",
    "booking_hero_tail": "zaczyna się tutaj",
    "booking_hero_text": "Wybierz trasę i zarezerwuj prywatną wyprawę po Mangystau.",
    "private_tour": "Wycieczka prywatna",
    "guests_1_3": "1–3 gości",
    "one_fixed_price": "Jedna stała cena",
    "book_your_tour": "Zarezerwuj wycieczkę",
    "form_intro": "Uzupełnij dane i wybierz trasę.",

    "msg_ok": "Dziękujemy! Otrzymaliśmy zgłoszenie i wkrótce się odezwiemy.",
    "msg_name": "Podaj swoje imię.",
    "msg_phone": "Podaj numer telefonu.",
    "msg_email": "Podaj poprawny adres e-mail.",
    "msg_date": "Wybierz datę wyjazdu.",
    "msg_date_format": "Nieprawidłowy format daty.",
    "msg_date_past": "Wybierz datę w przyszłości.",
    "msg_date_far": "Wybierz datę w ciągu najbliższych 18 miesięcy.",
    "msg_tour": "Wybierz wycieczkę z listy.",
    "msg_package": "Wybierz pakiet.",
    "msg_guests": "Liczba gości musi wynosić od 1 do {max}.",
    "msg_groups": "Liczba grup musi wynosić od 1 do {max}.",
    "msg_route": "Wybierz trasę dla tej wycieczki.",

    "group_note": "Jedna grupa to maksymalnie 3 gości. Od 4. gościa doliczana jest dopłata zależna od długości wycieczki.",
    "groups": "Grupy",
    "extra_guest_fee": "Dopłata za gościa",
    "extra_guests": "Dodatkowi goście",
    "extra_services": "Usługi dodatkowe",
    "extra_services_text": "Opcjonalne, doliczane do sumy. Usługi dzienne liczone są za każdy dzień wycieczki.",
    "services_price": "Usługi dodatkowe",
    "once": "jednorazowo",
    "per_day": "za dzień",
    "per_person": "za osobę",
    "base_price": "Wycieczka i pakiet",
    "groups_label": "Liczba grup",
    "groups_note": "Jedna grupa = jeden samochód, do 3 gości. Druga grupa podwaja cenę.",
    "group_word": "grupa",
    "groups_word": "grupy",
    "up_to_guests": "do {n} gości",
    "guests_label": "Liczba gości",
    "guests_hint": "Do 3 osób na samochód",

    "distance_note": "ok.",
    "rain_short": "Niedostępne podczas deszczu",
    "dress_short": "Wymagany zakryty strój",
    "choose_route": "Wybierz trasę",
    "choose_route_text": "Jeden dzień, jedna trasa. Wybierz tę, która najbardziej Ci odpowiada.",
    "route_label": "Trasa",
    "select_route": "Wybierz trasę",
    "book_this_route": "Zarezerwuj tę trasę",
    "rain_title": "Deszcz i siła wyższa",
    "rain_text": "Przy deszczowej pogodzie niektóre miejsca są zamknięte ze względów bezpieczeństwa: Tuzbair, góra Bokty i dolna część Bozzhyry. Przewodnik zaproponuje wtedy alternatywę tego samego dnia.",
    "dress_title": "Zwiedzanie meczetów",
    "dress_text": "Szakpak-Ata i Karaman-Ata to czynne meczety podziemne. Prosimy o zakryty strój: ramiona i kolana zasłonięte. Kobietom zalecamy chustę na głowę.",

    "overview": "O wycieczce",
    "overview_text": "Wszystko, co warto wiedzieć przed wyjazdem.",
    "included_title": "Co jest wliczone",
    "extras_title": "Dostępne za dopłatą",
    "start_point": "Aktau — hotel lub lotnisko",
    "group_size": "1–3 gości na samochód",
    "vehicle_type": "Przygotowany 4×4",

    "confirm_24h": "Potwierdzenie w ciągu 24 godzin",
    "pay_after": "Płatność po potwierdzeniu",
    "tour_price_label": "Cena wycieczki",
    "your_booking": "Twoja rezerwacja",
    "pick_tour_first": "Wybierz wycieczkę, aby zobaczyć szczegóły.",
    "summary_package": "Pakiet",
    "summary_route": "Trasa",
    "summary_groups": "Grupy",
    "summary_date": "Data",
    "summary_total": "Razem",
    "contacts_step": "Kontakt",
    "trip_step": "Twoja podróż",
    "not_selected": "Nie wybrano",
    "select_tour_hint": "Wybierz z listy",
    "sending": "Wysyłanie",
    "sent": "Zgłoszenie wysłane",

    "currency_note": "Orientacyjnie, po aktualnym kursie",
    "currency": "Waluta",
    "all_points": "Wszystkie miejsca",
    "map_filter": "Pokaż trasę",
})


TRANSLATIONS["ja"].update({
    "benefit_3_title": "快適さ",
    "moments_label": "マンギスタウ",
    "tour_duration_label": "所要日数",
    "tour_transport": "移動手段",
    "tour_group": "グループ",
    "tour_region": "地域",
    "one_day": "1日",
    "routes_title": "1日ルート",
    "route_1": "ウビクティ・サイ — トゥズバイル",
    "route_2": "トリシュ — トゥズバイル",
    "route_2_note": "雨天時はトゥズバイル下部へは下りません。",
    "route_3": "カパムサイ — シャクパク・アタ — トリシュ — ココラ — シェルカラ — アイラクティ",
    "route_4": "ウビクティ・サイ — クズルクプ — ボズジラ",
    "route_5": "クズルクプ — ボクティ — ボズジラ",
    "route_5_note": "雨天時はボクティには行きません。",
    "tour_price_note": "料金は選んだルートによって変わります。",
    "tour_includes": "ツアーに含まれるもの",
    "include_4x4": "4×4オフロード車",
    "include_guide": "現地ガイド",
    "include_support": "全行程のサポート",
    "include_water": "飲料水",
    "tour_2day_title": "2日間ジープ遠征",
    "tour_2day_description": "マンギスタウを代表する風景をめぐるオフロードの旅。快適さ、安全、そして忘れられない絶景。",
    "per_tour": "1ツアーあたり",
    "vehicle": "車両",
    "start_end": "出発 / 到着",
    "day": "日目",
    "meals": "食事",
    "stay": "宿泊",
    "day1_route": "アクタウ • カラムサイ • シャクパク・アタ • トリシュ • ココラ • シェルカラ • アイラクティ",
    "day1_text": "ホテルまたはアクタウ空港でガイドと合流します。最初にカラムサイ渓谷へ、続いてカスピ海を望む白亜の崖に彫られたシャクパク・アタ地下モスクを訪ねます。その後、直径4メートルにもなる丸い石の塊が点在するトリシュ渓谷へ。シェルカラ山で写真休憩をとり、未舗装路を進んでアイラクティの「城の谷」に到着します。",
    "day1_meals": "軽食、現地での夕食",
    "day1_stay": "星空の下のテント",
    "day2_route": "ボズジラ • ボクティ • クズルクプ",
    "day2_text": "朝、古代テチス海の名残が生んだ絶景で知られるボズジラへ向かいます。アクタウとは10〜15℃気温が違うことがあるため、暖かい服装をご用意ください。その後、草原にそびえる縞模様のピラミッド、ボクティ山へ。さらに白亜と鉄の地層が鮮やかな色を描くクズルクプを訪れ、夕方アクタウへ戻ります。",
    "day2_meals": "朝食、軽めの昼食",
    "day2_stay": "アクタウ、夕方",
    "what_included": "含まれるもの",
    "additional": "オプション",
    "include_transfer": "4×4送迎",
    "include_experienced_guide": "経験豊富なガイド",
    "include_entrance": "すべての入場料",
    "include_snacks": "軽食と飲み物",
    "include_tents": "テント",
    "include_sleeping": "寝袋とマット",
    "include_lighting": "キャンプ照明",
    "include_camping": "キャンプ用品",
    "include_refrigerator": "冷蔵庫",
    "include_drone": "ドローン撮影",
    "include_photo": "写真サポート",
    "additional_guide": "英語ガイド",
    "on_request": "リクエストに応じて",

    "back_to_site": "サイトに戻る",
    "menu": "メニュー",
    "language": "言語",
    "close": "閉じる",
    "skip": "本文へ移動",
    "email": "メールアドレス",
    "phone_placeholder": "700 000 00 00",
    "country_code": "国番号",
    "tour_date": "出発日",
    "guests_note": "1グループにつき3名まで。4名目からは追加料金がかかります。",
    "total_price": "合計",
    "required_note": "* の項目は必須です。",
    "price_from": "料金",
    "price_on_request": "料金はお問い合わせください",
    "tour_label": "ツアー",
    "view_tour": "ツアーを見る",
    "map_label": "地図",
    "route": "ルート",
    "routes": "ルート",
    "days": "日間",
    "stop": "立ち寄り",
    "discover_mangystau": "マンギスタウを発見する",

    "package": "プラン",
    "packages": "プラン",
    "packages_title": "プランを選ぶ",
    "packages_text": "ルートは同じ。快適さと撮影サービスのレベルが異なります。",
    "package_includes": "含まれるもの",
    "most_popular": "人気No.1",
    "select_package": "選ぶ",

    "booking_kicker": "予約",
    "booking_hero_lead": "あなたの",
    "booking_hero_accent": "旅",
    "booking_hero_tail": "はここから",
    "booking_hero_text": "ルートを選んで、マンギスタウのプライベートツアーを予約しましょう。",
    "private_tour": "プライベートツアー",
    "guests_1_3": "1〜3名",
    "one_fixed_price": "均一料金",
    "book_your_tour": "ツアーを予約する",
    "form_intro": "情報を入力し、ルートをお選びください。",

    "msg_ok": "ありがとうございます。リクエストを受け付けました。追ってご連絡します。",
    "msg_name": "お名前をご入力ください。",
    "msg_phone": "電話番号をご入力ください。",
    "msg_email": "有効なメールアドレスをご入力ください。",
    "msg_date": "出発日をお選びください。",
    "msg_date_format": "日付の形式が正しくありません。",
    "msg_date_past": "未来の日付をお選びください。",
    "msg_date_far": "今後18か月以内の日付をお選びください。",
    "msg_tour": "リストからツアーをお選びください。",
    "msg_package": "プランをお選びください。",
    "msg_guests": "人数は1〜{max}名の範囲でご指定ください。",
    "msg_groups": "グループ数は1〜{max}の範囲でご指定ください。",
    "msg_route": "このツアーのルートをお選びください。",

    "group_note": "1グループは3名までです。4名目からはツアーの日数に応じた追加料金がかかります。",
    "groups": "グループ",
    "extra_guest_fee": "追加人数料金",
    "extra_guests": "追加のお客様",
    "extra_services": "追加サービス",
    "extra_services_text": "任意です。合計に加算されます。日額サービスはツアーの日数分が計算されます。",
    "services_price": "追加サービス",
    "once": "1回のみ",
    "per_day": "1日あたり",
    "per_person": "1名あたり",
    "base_price": "ツアーとプラン",
    "groups_label": "グループ数",
    "groups_note": "1グループ＝1台、3名まで。2グループ目で料金は2倍になります。",
    "group_word": "グループ",
    "groups_word": "グループ",
    "up_to_guests": "{n}名まで",
    "guests_label": "人数",
    "guests_hint": "1台につき3名まで",

    "distance_note": "約",
    "rain_short": "雨天時は立ち入り不可",
    "dress_short": "肌を覆う服装が必要",
    "choose_route": "ルートを選ぶ",
    "choose_route_text": "1日に1ルート。お好みのルートをお選びください。",
    "route_label": "ルート",
    "select_route": "ルートを選択",
    "book_this_route": "このルートを予約する",
    "rain_title": "雨天と不可抗力について",
    "rain_text": "雨天時は安全のため、トゥズバイル、ボクティ山、ボズジラ下部へは立ち入れません。ガイドが同じ日に代わりの立ち寄り先をご案内します。",
    "dress_title": "モスクの見学について",
    "dress_text": "シャクパク・アタとカラマン・アタは現在も使われている地下モスクです。肩と膝が隠れる服装をお願いします。女性はスカーフをご用意ください。",

    "overview": "ツアー概要",
    "overview_text": "出発前に知っておきたいことをまとめました。",
    "included_title": "含まれるもの",
    "extras_title": "追加料金で利用可能",
    "start_point": "アクタウ — ホテルまたは空港",
    "group_size": "1台につき1〜3名",
    "vehicle_type": "整備済みの4×4",

    "confirm_24h": "24時間以内に確認のご連絡",
    "pay_after": "お支払いは確認後",
    "tour_price_label": "ツアー料金",
    "your_booking": "ご予約内容",
    "pick_tour_first": "ツアーを選ぶと詳細が表示されます。",
    "summary_package": "プラン",
    "summary_route": "ルート",
    "summary_groups": "グループ",
    "summary_date": "日付",
    "summary_total": "合計",
    "contacts_step": "連絡先",
    "trip_step": "ご旅行について",
    "not_selected": "未選択",
    "select_tour_hint": "リストから選択",
    "sending": "送信中",
    "sent": "リクエスト送信済み",

    "currency_note": "現在のレートによる概算です",
    "currency": "通貨",
    "all_points": "すべての場所",
    "map_filter": "ルートを表示",
})

# ===========================================================================
# ДЕРЕКТЕРДІҢ АУДАРМАСЫ: IT / FR / PL / JA
# ---------------------------------------------------------------------------
# Пакеттердің құрамы, қосымша қызметтер және картадағы сипаттамалар
# бұрын тек kz / ru / en / zh тілінде болатын. Мұнда қалған төрт тіл
# қосылады.
#
# Жұмыс принципі: ағылшын мәтіні кілт ретінде алынады да, сол мәтін
# кездескен жердің бәріне аударма қосылады. Сондықтан жаңа пакет
# немесе қызмет қосқанда, оның ағылшыншасын осы тізімге қоссаң
# жеткілікті — қалғанын код өзі табады.
# ===========================================================================

DATA_TRANSLATIONS = {

    # --- пакеттердің сипаттамасы ---
    "The route itself, done properly.": {
        "it": "Il percorso vero e proprio, fatto come si deve.",
        "fr": "L'itinéraire lui-même, fait comme il faut.",
        "pl": "Sama trasa, zrobiona porządnie.",
        "ja": "ルートそのものを、しっかりと。",
    },
    "Everything in Basic, plus real photos of your trip.": {
        "it": "Tutto quello che c'è in Basic, più vere foto del tuo viaggio.",
        "fr": "Tout ce que comprend Basic, plus de vraies photos de votre voyage.",
        "pl": "Wszystko z pakietu Basic oraz prawdziwe zdjęcia z Twojej podróży.",
        "ja": "Basicの内容すべてに、旅の本格的な写真をプラス。",
    },
    "A separate guide and a full film crew for your trip.": {
        "it": "Una guida dedicata e una troupe completa per il tuo viaggio.",
        "fr": "Un guide dédié et une équipe de tournage complète pour votre voyage.",
        "pl": "Osobny przewodnik i pełna ekipa filmowa na Twoją wyprawę.",
        "ja": "専属ガイドと撮影チームが旅に同行します。",
    },

    # --- пакеттердің құрамы ---
    "Hotel pick-up (Aktau only)": {
        "it": "Prelievo in hotel (solo ad Aktau)",
        "fr": "Prise en charge à l'hôtel (Aktau uniquement)",
        "pl": "Odbiór z hotelu (tylko w Aktau)",
        "ja": "ホテルお迎え（アクタウ市内のみ）",
    },
    "4×4 vehicle with air conditioning": {
        "it": "Fuoristrada 4×4 con aria condizionata",
        "fr": "Véhicule 4×4 climatisé",
        "pl": "Samochód 4×4 z klimatyzacją",
        "ja": "エアコン付き4×4車",
    },
    "Comfortable camping equipment": {
        "it": "Attrezzatura da campeggio confortevole",
        "fr": "Matériel de camping confortable",
        "pl": "Wygodny sprzęt kempingowy",
        "ja": "快適なキャンプ用品",
    },
    "Comfortable travel equipment": {
        "it": "Attrezzatura da viaggio confortevole",
        "fr": "Matériel de voyage confortable",
        "pl": "Wygodny sprzęt podróżny",
        "ja": "快適な旅行用装備",
    },
    "Upgraded camping equipment": {
        "it": "Attrezzatura da campeggio di livello superiore",
        "fr": "Matériel de camping haut de gamme",
        "pl": "Ulepszony sprzęt kempingowy",
        "ja": "アップグレードされたキャンプ用品",
    },
    "Three meals a day": {
        "it": "Tre pasti al giorno",
        "fr": "Trois repas par jour",
        "pl": "Trzy posiłki dziennie",
        "ja": "1日3食",
    },
    "Three chef-prepared meals a day": {
        "it": "Tre pasti al giorno preparati dallo chef",
        "fr": "Trois repas par jour préparés par un chef",
        "pl": "Trzy posiłki dziennie przygotowane przez kucharza",
        "ja": "シェフが用意する1日3食",
    },
    "Water (1 l per person per day)": {
        "it": "Acqua (1 l a persona al giorno)",
        "fr": "Eau (1 l par personne et par jour)",
        "pl": "Woda (1 l na osobę dziennie)",
        "ja": "飲料水（1人1日1リットル）",
    },
    "Travel insurance": {
        "it": "Assicurazione di viaggio",
        "fr": "Assurance voyage",
        "pl": "Ubezpieczenie turystyczne",
        "ja": "旅行保険",
    },
    "Airport transfer": {
        "it": "Transfer dall'aeroporto",
        "fr": "Transfert depuis l'aéroport",
        "pl": "Transfer z lotniska",
        "ja": "空港送迎",
    },
    "Meeting at your hotel": {
        "it": "Incontro in hotel",
        "fr": "Accueil à votre hôtel",
        "pl": "Spotkanie w hotelu",
        "ja": "ホテルでのお出迎え",
    },
    "Hotel transfer": {
        "it": "Transfer dall'hotel",
        "fr": "Transfert depuis l'hôtel",
        "pl": "Transfer z hotelu",
        "ja": "ホテル送迎",
    },
    "Local English-speaking guide": {
        "it": "Guida locale di lingua inglese",
        "fr": "Guide local anglophone",
        "pl": "Lokalny przewodnik anglojęzyczny",
        "ja": "英語を話す現地ガイド",
    },
    "Camping toilet": {
        "it": "Toilette da campeggio",
        "fr": "Toilettes de camp",
        "pl": "Toaleta kempingowa",
        "ja": "キャンプ用トイレ",
    },
    "Camping shower": {
        "it": "Doccia da campeggio",
        "fr": "Douche de camp",
        "pl": "Prysznic kempingowy",
        "ja": "キャンプ用シャワー",
    },
    "Drone filming": {
        "it": "Riprese con drone",
        "fr": "Prises de vue par drone",
        "pl": "Ujęcia z drona",
        "ja": "ドローン撮影",
    },
    "Generator for charging devices": {
        "it": "Generatore per ricaricare i dispositivi",
        "fr": "Générateur pour recharger les appareils",
        "pl": "Generator do ładowania urządzeń",
        "ja": "機器充電用の発電機",
    },
    "Wi-Fi": {
        "it": "Wi-Fi", "fr": "Wi-Fi", "pl": "Wi-Fi", "ja": "Wi-Fi",
    },

    # --- қосымша қызметтер ---
    "Starlink internet": {
        "it": "Internet Starlink",
        "fr": "Internet Starlink",
        "pl": "Internet Starlink",
        "ja": "スターリンク・インターネット",
    },
    "English or Chinese speaking guide": {
        "it": "Guida di lingua inglese o cinese",
        "fr": "Guide anglophone ou sinophone",
        "pl": "Przewodnik anglo- lub chińskojęzyczny",
        "ja": "英語または中国語ガイド",
    },
    "Shower": {
        "it": "Doccia", "fr": "Douche", "pl": "Prysznic", "ja": "シャワー",
    },
    "Portable toilet": {
        "it": "Toilette portatile",
        "fr": "Toilettes portatives",
        "pl": "Toaleta przenośna",
        "ja": "移動式トイレ",
    },
    "Camp generator for charging devices": {
        "it": "Generatore da campo per ricaricare i dispositivi",
        "fr": "Générateur de camp pour recharger les appareils",
        "pl": "Generator obozowy do ładowania urządzeń",
        "ja": "機器充電用のキャンプ発電機",
    },

    # --- картадағы сипаттамалар ---
    "Starting point of the journey.": {
        "it": "Punto di partenza del viaggio.",
        "fr": "Point de départ du voyage.",
        "pl": "Punkt startowy wyprawy.",
        "ja": "旅の出発地点。",
    },
    "Karamsai canyon.": {
        "it": "Canyon di Karamsai.",
        "fr": "Canyon de Karamsaï.",
        "pl": "Kanion Karamsaj.",
        "ja": "カラムサイ渓谷。",
    },
    "Shakpak-Ata underground mosque.": {
        "it": "Moschea sotterranea di Shakpak-Ata.",
        "fr": "Mosquée souterraine de Chakpak-Ata.",
        "pl": "Podziemny meczet Szakpak-Ata.",
        "ja": "シャクパク・アタ地下モスク。",
    },
    "Valley of mysterious stone balls.": {
        "it": "Valle delle misteriose sfere di pietra.",
        "fr": "Vallée des mystérieuses boules de pierre.",
        "pl": "Dolina tajemniczych kamiennych kul.",
        "ja": "謎の石球が広がる谷。",
    },
    "Colourful geological formations.": {
        "it": "Formazioni geologiche variopinte.",
        "fr": "Formations géologiques colorées.",
        "pl": "Barwne formacje geologiczne.",
        "ja": "色鮮やかな地層。",
    },
    "The famous Mount Sherkala.": {
        "it": "Il celebre monte Sherkala.",
        "fr": "Le célèbre mont Cherkala.",
        "pl": "Słynna góra Szerkala.",
        "ja": "有名なシェルカラ山。",
    },
    "Airakty — Valley of Castles.": {
        "it": "Airakty — la Valle dei Castelli.",
        "fr": "Aïrakty — la vallée des Châteaux.",
        "pl": "Airakty — Dolina Zamków.",
        "ja": "アイラクティ — 城の谷。",
    },
    "One of the most iconic landscapes of Mangystau.": {
        "it": "Uno dei paesaggi più iconici del Mangystau.",
        "fr": "L'un des paysages les plus emblématiques du Mangystau.",
        "pl": "Jeden z najbardziej rozpoznawalnych krajobrazów Mangystau.",
        "ja": "マンギスタウを代表する風景のひとつ。",
    },
    "Mount Bokty.": {
        "it": "Monte Bokty.",
        "fr": "Mont Bokty.",
        "pl": "Góra Bokty.",
        "ja": "ボクティ山。",
    },
    "Karaman-Ata underground mosque and necropolis.": {
        "it": "Moschea sotterranea e necropoli di Karaman-Ata.",
        "fr": "Mosquée souterraine et nécropole de Karaman-Ata.",
        "pl": "Podziemny meczet i nekropolia Karaman-Ata.",
        "ja": "カラマン・アタ地下モスクと墓地。",
    },
    "Kyzylkup — the Mangystau Tiramisu.": {
        "it": "Kyzylkup — il «tiramisù» del Mangystau.",
        "fr": "Kyzylkoup — le « tiramisu » du Mangystau.",
        "pl": "Kyzyłkup — „tiramisu” Mangystau.",
        "ja": "クズルクプ — マンギスタウのティラミス。",
    },
    "Tuzbair salt marsh — white plains framed by limestone cliffs.": {
        "it": "Salina di Tuzbair — pianure bianche incorniciate da falesie calcaree.",
        "fr": "Marais salant de Touzbaïr — plaines blanches encadrées de falaises calcaires.",
        "pl": "Solnisko Tuzbair — białe równiny otoczone wapiennymi klifami.",
        "ja": "トゥズバイル塩原 — 石灰岩の崖に囲まれた白い平原。",
    },
    "Ybykty-Sai canyon.": {
        "it": "Canyon di Ybykty-Sai.",
        "fr": "Canyon d'Ybykty-Saï.",
        "pl": "Kanion Ybykty-Saj.",
        "ja": "ウビクティ・サイ渓谷。",
    },
    "Akespe — a village at the foot of white chalk cliffs.": {
        "it": "Akespe — un villaggio ai piedi di bianche falesie di gesso.",
        "fr": "Akespé — un village au pied de falaises de craie blanche.",
        "pl": "Akespe — wieś u podnóża białych kredowych klifów.",
        "ja": "アケスペ — 白亜の崖のふもとにある村。",
    },
    "Tuyesu sand dunes.": {
        "it": "Dune di sabbia di Tuyesu.",
        "fr": "Dunes de sable de Touyesou.",
        "pl": "Wydmy Tujesu.",
        "ja": "トゥイェス砂丘。",
    },
}


def _enrich(value):
    """
    {"en": "...", "ru": "..."} сөздігіне жоқ тілдерді қосады.
    Ағылшын мәтіні DATA_TRANSLATIONS ішінде табылса ғана.
    """
    if not isinstance(value, dict):
        return value

    source = value.get("en")
    extra = DATA_TRANSLATIONS.get(source)

    if not extra:
        return value

    for lang, text in extra.items():
        value.setdefault(lang, text)

    return value


def _enrich_all():
    """Пакеттер, қызметтер және карта нүктелерін толықтырады."""

    for package in PACKAGES:
        _enrich(package.get("tagline"))
        for feature in package.get("features", []):
            _enrich(feature)

    for service in SERVICES:
        _enrich(service.get("name"))

    for point in MAP_POINTS:
        _enrich(point.get("text"))

    for items in ROUTE_FALLBACK.values():
        for item in items:
            _enrich(item.get("title"))
            _enrich(item.get("note"))
            _enrich(item.get("desc"))


_enrich_all()


# =========================================================
# EXTRA TEXTS
# =========================================================
# Жаңа шаблондарға керек кілттер (пакеттер, форма, хабарламалар).
# Аудармасы жоқ тіл EN нұсқасын алады — Tr класы төменде.

EXTRA_TEXTS = {

    "en": {
        "back": "Back",
        "back_to_site": "Back to website",
        "menu": "Menu",
        "language": "Language",
        "close": "Close",
        "skip": "Skip to content",
        "email": "Email",
        "phone_placeholder": "700 000 00 00",
        "country_code": "Country code",
        "tour_date": "Date of tour",
        "guests_note": "Up to 3 guests per group. From the 4th guest an extra fee applies.",
        "total_price": "Total price",
        "required_note": "Fields marked with * are required.",
        "price_from": "Price from",
        "price_on_request": "Price on request",
        "tour_label": "Tour",
        "view_tour": "View tour",
        "map_label": "Map",
        "route": "Route",
        "routes": "Routes",
        "days": "Days",
        "stop": "Stop",
        "discover_mangystau": "Discover Mangystau",

        "package": "Package",
        "packages": "Packages",
        "packages_title": "Choose your package",
        "packages_text": "Same route, different level of comfort and media coverage.",
        "package_includes": "Includes",
        "most_popular": "Most popular",
        "select_package": "Choose",

        "booking_kicker": "Booking",
        "booking_hero_lead": "Your",
        "booking_hero_accent": "journey",
        "booking_hero_tail": "starts here",
        "booking_hero_text": "Choose your route and reserve your private Mangystau experience.",
        "private_tour": "Private tour",
        "guests_1_3": "1–3 guests",
        "one_fixed_price": "One fixed price",
        "book_your_tour": "Book your tour",
        "form_intro": "Fill in your details and choose your route.",

        "msg_ok": "Thank you. We received your request and will contact you shortly.",
        "msg_name": "Please enter your name.",
        "msg_phone": "Please enter your phone number.",
        "msg_email": "Please enter a valid email address.",
        "msg_date": "Please choose a date for the tour.",
        "msg_date_format": "Invalid date format.",
        "msg_date_past": "Please choose a date in the future.",
        "msg_date_far": "Please choose a date within the next 18 months.",
        "msg_tour": "Please select a tour from the list.",
        "msg_package": "Please select a package.",
        "msg_guests": "Number of guests must be between 1 and {max}.",

        "group_note": "One vehicle takes up to 3 guests. From the 4th guest an extra fee is added.",
        "groups": "Vehicles",
        "extra_guest_fee": "Extra guests",
        "extra_services": "Additional services",
        "extra_services_text": "Optional. Per-day services are multiplied by the length of the tour.",
        "services_price": "Additional services",
        "once": "one time",
        "distance_note": "Distance is approximate and depends on weather and road conditions.",
        "rain_short": "Not visited in rain",
        "dress_short": "Covered clothing required",

        "choose_route": "Choose your route",
        "choose_route_text": "One day, one route. Pick the one you like most.",
        "route_label": "Route",
        "select_route": "Choose route",
        "msg_route": "Please choose a route for this tour.",
        "book_this_route": "Book this route",

        "overview": "Tour overview",
        "overview_text": "Everything you need to know before the trip.",
        "included_title": "What is included",
        "extras_title": "Available for an extra fee",
        "start_point": "Aktau — hotel or airport",
        "group_size": "1–3 guests per vehicle",
        "vehicle_type": "Prepared 4×4",

        "groups_label": "Number of groups",
        "groups_note": "One group = one vehicle, up to 3 guests. A second group doubles the price.",
        "group_word": "group",
        "groups_word": "groups",
        "up_to_guests": "up to {n} guests",
        "confirm_24h": "Confirmation within 24 hours",
        "pay_after": "Payment after confirmation",
        "tour_price_label": "Tour price",

        "your_booking": "Your booking",
        "pick_tour_first": "Choose a tour to see the details here.",
        "summary_package": "Package",
        "summary_route": "Route",
        "summary_groups": "Groups",
        "summary_date": "Date",
        "summary_total": "Total",
        "contacts_step": "Contacts",
        "trip_step": "Your trip",
        "not_selected": "Not selected",

        "currency_note": "Approximate, at the current rate",
        "currency": "Currency",

        "all_points": "All places",
        "map_filter": "Show route of",

        "msg_groups": "Number of groups must be between 1 and {max}.",
        "guests_label": "Number of guests",
        "guests_hint": "Up to 3 per vehicle",
        "select_tour_hint": "Choose from the list",
        "sending": "Sending",
        "sent": "Request sent",

        "search_country": "Search country",

        "distance": "Distance",
        "distance_note": "approx.",
        "rain_title": "Rain and force majeure",
        "rain_text": "In rainy weather some places are closed for safety: Tuzbair, "
                     "Mount Bokty and the lower part of Bozzhyra. The guide replaces "
                     "them with an alternative stop on the same day.",
        "rain_short": "Closed in rainy weather",
        "dress_title": "Visiting the mosques",
        "dress_text": "Shakpak-Ata and Karaman-Ata are working underground mosques. "
                      "Please wear closed clothing: shoulders and knees covered. "
                      "A scarf is recommended for women.",
        "dress_short": "Closed clothing required",

        "group_note": "One group is up to 3 guests. From the 4th guest an extra "
                      "fee applies, depending on the tour length.",
        "extra_guests": "Extra guests",
        "extra_guest_fee": "Extra guest fee",
        "base_price": "Tour and package",
        "groups": "Groups",
        "per_person": "per person",

        "extra_services": "Extra services",
        "extra_services_text": "Optional, added to the total. Daily services are "
                               "charged for every day of the tour.",
        "per_day": "per day",
        "once": "one-time",
        "services_price": "Extra services",
    },

    "kz": {
        "back": "Артқа",
        "back_to_site": "Сайтқа оралу",
        "menu": "Мәзір",
        "language": "Тіл",
        "close": "Жабу",
        "skip": "Мазмұнға өту",
        "email": "Email",
        "phone_placeholder": "700 000 00 00",
        "country_code": "Ел коды",
        "tour_date": "Тур күні",
        "guests_note": "Бір топта 3 қонаққа дейін. 4-ші қонақтан бастап қосымша ақы.",
        "total_price": "Жалпы баға",
        "required_note": "* белгісі қойылған өрістер міндетті.",
        "price_from": "Бағасы",
        "price_on_request": "Баға сұраныс бойынша",
        "tour_label": "Тур",
        "view_tour": "Турды көру",
        "map_label": "Карта",
        "route": "Бағыт",
        "routes": "Бағыттар",
        "days": "Күн",
        "stop": "Аялдама",
        "discover_mangystau": "Маңғыстауды ашыңыз",

        "package": "Пакет",
        "packages": "Пакеттер",
        "packages_title": "Пакетті таңдаңыз",
        "packages_text": "Маршрут бірдей — қызмет пен түсірілім деңгейі әртүрлі.",
        "package_includes": "Құрамында",
        "most_popular": "Ең сұранысқа ие",
        "select_package": "Таңдау",

        "booking_kicker": "Брондау",
        "booking_hero_lead": "Сапарыңыз",
        "booking_hero_accent": "осы жерден",
        "booking_hero_tail": "басталады",
        "booking_hero_text": "Бағытты таңдап, жеке сапарыңызды брондаңыз.",
        "private_tour": "Жеке тур",
        "guests_1_3": "1–3 қонақ",
        "one_fixed_price": "Бір тұрақты баға",
        "book_your_tour": "Тур брондау",
        "form_intro": "Мәліметтеріңізді толтырып, бағытты таңдаңыз.",

        "msg_ok": "Рақмет! Өтінішіңіз қабылданды, жақын арада хабарласамыз.",
        "msg_name": "Атыңызды жазыңыз.",
        "msg_phone": "Телефон нөмірін жазыңыз.",
        "msg_email": "Жарамды email мекенжайын енгізіңіз.",
        "msg_date": "Тур күнін таңдаңыз.",
        "msg_date_format": "Күн форматы дұрыс емес.",
        "msg_date_past": "Болашақтағы күнді таңдаңыз.",
        "msg_date_far": "Алдағы 18 ай ішіндегі күнді таңдаңыз.",
        "msg_tour": "Тізімнен турды таңдаңыз.",
        "msg_package": "Пакетті таңдаңыз.",
        "msg_guests": "Қонақ саны 1-ден {max}-ге дейін болуы керек.",

        "group_note": "Бір көлікке 3 қонаққа дейін. 4-ші қонақтан бастап қосымша ақы қосылады.",
        "groups": "Көлік",
        "extra_guest_fee": "Қосымша қонақ",
        "extra_services": "Қосымша қызметтер",
        "extra_services_text": "Қалауыңыз бойынша. Күндік қызметтер тур ұзақтығына көбейтіледі.",
        "services_price": "Қосымша қызметтер",
        "once": "бір рет",
        "distance_note": "Қашықтық шамамен, ауа райы мен жол жағдайына байланысты өзгереді.",
        "rain_short": "Жаңбырда барылмайды",
        "dress_short": "Жабық киім қажет",

        "choose_route": "Бағытты таңдаңыз",
        "choose_route_text": "Бір күн — бір бағыт. Ұнағанын таңдаңыз.",
        "route_label": "Бағыт",
        "select_route": "Бағытты таңдау",
        "msg_route": "Осы турға бағыт таңдаңыз.",
        "book_this_route": "Осы бағытты брондау",

        "overview": "Тур туралы",
        "overview_text": "Сапарға дейін білуге қажет негізгі мәліметтер.",
        "included_title": "Бағаға не кіреді",
        "extras_title": "Қосымша ақыға",
        "start_point": "Ақтау — қонақүй немесе әуежай",
        "group_size": "Бір көлікке 1–3 қонақ",
        "vehicle_type": "Дайындалған 4×4",

        "groups_label": "Топ саны",
        "groups_note": "Бір топ = бір көлік, 3 қонаққа дейін. Екінші топ қосылса, баға еселенеді.",
        "group_word": "топ",
        "groups_word": "топ",
        "up_to_guests": "{n} қонаққа дейін",
        "confirm_24h": "24 сағат ішінде растаймыз",
        "pay_after": "Төлем растағаннан кейін",
        "tour_price_label": "Тур бағасы",

        "your_booking": "Сіздің брондауыңыз",
        "pick_tour_first": "Мәліметтерді көру үшін турды таңдаңыз.",
        "summary_package": "Пакет",
        "summary_route": "Бағыт",
        "summary_groups": "Топ",
        "summary_date": "Күні",
        "summary_total": "Барлығы",
        "contacts_step": "Байланыс",
        "trip_step": "Сапарыңыз",
        "not_selected": "Таңдалмаған",

        "currency_note": "Ағымдағы курс бойынша шамамен",
        "currency": "Валюта",

        "all_points": "Барлық орын",
        "map_filter": "Маршрутты көрсету",

        "msg_groups": "Топ саны 1-ден {max}-ке дейін болуы керек.",
        "guests_label": "Қонақ саны",
        "guests_hint": "Бір көлікке 3 адамға дейін",
        "select_tour_hint": "Тізімнен таңдаңыз",
        "sending": "Жіберілуде",
        "sent": "Өтінім жіберілді",

        "search_country": "Елді іздеу",

        "distance": "Қашықтық",
        "distance_note": "шамамен",
        "rain_title": "Жаңбыр және форс-мажор",
        "rain_text": "Жаңбырлы ауа райында кейбір жерлерге қауіпсіздік үшін "
                     "бармаймыз: Тұзбайыр, Боқты тауы және төменгі Бозжыра. "
                     "Гид сол күні орнына басқа орын ұсынады.",
        "rain_short": "Жаңбырда жабық",
        "dress_title": "Мешітке кіру ережесі",
        "dress_text": "Шақпақ-Ата және Қараман-Ата — жұмыс істеп тұрған жерасты "
                      "мешіттері. Жабық киім киіңіз: иық пен тізе жабылуы керек. "
                      "Әйелдерге орамал ұсынылады.",
        "dress_short": "Жабық киім қажет",

        "group_note": "Бір топта 3 қонаққа дейін. 4-ші қонақтан бастап турдың "
                      "ұзақтығына қарай қосымша ақы қосылады.",
        "extra_guests": "Қосымша қонақ",
        "extra_guest_fee": "Қосымша қонақ ақысы",
        "base_price": "Тур және пакет",
        "groups": "Топ саны",
        "per_person": "бір адамға",

        "extra_services": "Қосымша қызметтер",
        "extra_services_text": "Қалауыңыз бойынша, жалпы бағаға қосылады. "
                               "Күндік қызметтер турдың әр күніне есептеледі.",
        "per_day": "күніне",
        "once": "бір рет",
        "services_price": "Қосымша қызметтер",
    },

    "ru": {
        "back": "Назад",
        "back_to_site": "Вернуться на сайт",
        "menu": "Меню",
        "language": "Язык",
        "close": "Закрыть",
        "skip": "Перейти к содержимому",
        "email": "Email",
        "phone_placeholder": "700 000 00 00",
        "country_code": "Код страны",
        "tour_date": "Дата тура",
        "guests_note": "До 3 гостей в группе. С 4-го гостя — доплата.",
        "total_price": "Итоговая цена",
        "required_note": "Поля со знаком * обязательны.",
        "price_from": "Цена от",
        "price_on_request": "Цена по запросу",
        "tour_label": "Тур",
        "view_tour": "Смотреть тур",
        "map_label": "Карта",
        "route": "Маршрут",
        "routes": "Маршруты",
        "days": "Дней",
        "stop": "Остановка",
        "discover_mangystau": "Откройте Мангистау",

        "package": "Пакет",
        "packages": "Пакеты",
        "packages_title": "Выберите пакет",
        "packages_text": "Маршрут тот же — отличается уровень сервиса и съёмки.",
        "package_includes": "Включено",
        "most_popular": "Чаще всего выбирают",
        "select_package": "Выбрать",

        "booking_kicker": "Бронирование",
        "booking_hero_lead": "Ваше",
        "booking_hero_accent": "путешествие",
        "booking_hero_tail": "начинается здесь",
        "booking_hero_text": "Выберите маршрут и забронируйте индивидуальный тур по Мангистау.",
        "private_tour": "Индивидуальный тур",
        "guests_1_3": "1–3 гостя",
        "one_fixed_price": "Одна фиксированная цена",
        "book_your_tour": "Забронировать тур",
        "form_intro": "Заполните данные и выберите маршрут.",

        "msg_ok": "Спасибо! Заявка получена, мы свяжемся с вами в ближайшее время.",
        "msg_name": "Пожалуйста, укажите имя.",
        "msg_phone": "Пожалуйста, укажите телефон.",
        "msg_email": "Пожалуйста, укажите корректный Email.",
        "msg_date": "Пожалуйста, выберите дату тура.",
        "msg_date_format": "Неверный формат даты.",
        "msg_date_past": "Выберите дату в будущем.",
        "msg_date_far": "Выберите дату в пределах ближайших 18 месяцев.",
        "msg_tour": "Пожалуйста, выберите тур из списка.",
        "msg_package": "Пожалуйста, выберите пакет.",
        "msg_guests": "Количество гостей — от 1 до {max}.",

        "group_note": "В одной машине до 3 гостей. С 4-го гостя добавляется доплата.",
        "groups": "Машин",
        "extra_guest_fee": "Дополнительные гости",
        "extra_services": "Дополнительные услуги",
        "extra_services_text": "По желанию. Услуги «в день» умножаются на длительность тура.",
        "services_price": "Дополнительные услуги",
        "once": "разово",
        "distance_note": "Расстояние приблизительное и зависит от погоды и состояния дорог.",
        "rain_short": "Не посещается в дождь",
        "dress_short": "Нужна закрытая одежда",

        "choose_route": "Выберите маршрут",
        "choose_route_text": "Один день — один маршрут. Выберите тот, что вам ближе.",
        "route_label": "Маршрут",
        "select_route": "Выбрать маршрут",
        "msg_route": "Пожалуйста, выберите маршрут для этого тура.",
        "book_this_route": "Забронировать этот маршрут",

        "overview": "О туре",
        "overview_text": "Всё, что нужно знать перед поездкой.",
        "included_title": "Что входит в стоимость",
        "extras_title": "За дополнительную плату",
        "start_point": "Актау — отель или аэропорт",
        "group_size": "1–3 гостя в машине",
        "vehicle_type": "Подготовленный 4×4",

        "groups_label": "Количество групп",
        "groups_note": "Одна группа = одна машина, до 3 гостей. Вторая группа удваивает стоимость.",
        "group_word": "группа",
        "groups_word": "группы",
        "up_to_guests": "до {n} гостей",
        "confirm_24h": "Подтверждение в течение 24 часов",
        "pay_after": "Оплата после подтверждения",
        "tour_price_label": "Стоимость тура",

        "your_booking": "Ваше бронирование",
        "pick_tour_first": "Выберите тур, чтобы увидеть детали здесь.",
        "summary_package": "Пакет",
        "summary_route": "Маршрут",
        "summary_groups": "Группы",
        "summary_date": "Дата",
        "summary_total": "Итого",
        "contacts_step": "Контакты",
        "trip_step": "Ваша поездка",
        "not_selected": "Не выбрано",

        "currency_note": "Примерно, по текущему курсу",
        "currency": "Валюта",

        "all_points": "Все места",
        "map_filter": "Показать маршрут",

        "msg_groups": "Количество групп — от 1 до {max}.",
        "guests_label": "Количество гостей",
        "guests_hint": "До 3 человек в машине",
        "select_tour_hint": "Выберите из списка",
        "sending": "Отправка",
        "sent": "Заявка отправлена",

        "search_country": "Поиск страны",

        "distance": "Расстояние",
        "distance_note": "примерно",
        "rain_title": "Дождь и форс-мажор",
        "rain_text": "В дождливую погоду часть локаций закрыта по соображениям "
                     "безопасности: Тузбаир, гора Бокты и нижняя Бозжыра. "
                     "Гид предложит альтернативную остановку в тот же день.",
        "rain_short": "Закрыто в дождь",
        "dress_title": "Посещение мечетей",
        "dress_text": "Шакпак-Ата и Караман-Ата — действующие подземные мечети. "
                      "Пожалуйста, наденьте закрытую одежду: плечи и колени должны "
                      "быть закрыты. Женщинам рекомендуется платок.",
        "dress_short": "Нужна закрытая одежда",

        "group_note": "В одной группе до 3 гостей. С 4-го гостя добавляется "
                      "доплата в зависимости от длительности тура.",
        "extra_guests": "Дополнительные гости",
        "extra_guest_fee": "Доплата за гостей",
        "base_price": "Тур и пакет",
        "groups": "Групп",
        "per_person": "за человека",

        "extra_services": "Дополнительные услуги",
        "extra_services_text": "По желанию, добавляются к итоговой цене. "
                               "Ежедневные услуги считаются за каждый день тура.",
        "per_day": "в день",
        "once": "разово",
        "services_price": "Дополнительные услуги",
    },

    "zh": {
        "back": "返回",
        "back_to_site": "返回网站",
        "menu": "菜单",
        "language": "语言",
        "close": "关闭",
        "skip": "跳到主要内容",
        "email": "电子邮箱",
        "phone_placeholder": "700 000 00 00",
        "country_code": "国家代码",
        "tour_date": "出行日期",
        "guests_note": "每组最多 3 人，从第 4 人起收取附加费。",
        "total_price": "总价",
        "required_note": "带 * 的为必填项。",
        "price_from": "价格起",
        "price_on_request": "价格面议",
        "tour_label": "线路",
        "view_tour": "查看线路",
        "map_label": "地图",
        "route": "路线",
        "routes": "路线",
        "days": "天",
        "stop": "站点",
        "discover_mangystau": "探索曼吉斯套",

        "package": "套餐",
        "packages": "套餐",
        "packages_title": "选择套餐",
        "packages_text": "路线相同，服务与拍摄级别不同。",
        "package_includes": "包含",
        "most_popular": "最受欢迎",
        "select_package": "选择",

        "booking_kicker": "预订",
        "booking_hero_lead": "您的",
        "booking_hero_accent": "旅程",
        "booking_hero_tail": "从这里开始",
        "booking_hero_text": "选择路线，预订您的曼吉斯套私人行程。",
        "private_tour": "私人行程",
        "guests_1_3": "1–3 位客人",
        "one_fixed_price": "统一价格",
        "book_your_tour": "预订行程",
        "form_intro": "填写您的信息并选择路线。",

        "msg_ok": "谢谢！我们已收到您的申请，会尽快与您联系。",
        "msg_name": "请填写您的姓名。",
        "msg_phone": "请填写您的电话号码。",
        "msg_email": "请输入有效的电子邮箱。",
        "msg_date": "请选择出行日期。",
        "msg_date_format": "日期格式无效。",
        "msg_date_past": "请选择未来的日期。",
        "msg_date_far": "请选择未来 18 个月内的日期。",
        "msg_tour": "请从列表中选择线路。",
        "msg_package": "请选择套餐。",
        "msg_guests": "人数必须在 1 至 {max} 之间。",

        "group_note": "每辆车最多 3 位客人，第 4 位客人起需加收费用。",
        "groups": "车辆",
        "extra_guest_fee": "额外客人",
        "extra_services": "附加服务",
        "extra_services_text": "可选。按天计费的服务将乘以行程天数。",
        "services_price": "附加服务",
        "once": "一次性",
        "distance_note": "距离为大致数值，会因天气和路况而变化。",
        "rain_short": "雨天不前往",
        "dress_short": "需着装遮体",

        "choose_route": "选择路线",
        "choose_route_text": "一天一条路线，选择您最喜欢的那条。",
        "route_label": "路线",
        "select_route": "选择路线",
        "msg_route": "请为该行程选择一条路线。",
        "book_this_route": "预订此路线",

        "overview": "行程概览",
        "overview_text": "出发前需要了解的全部信息。",
        "included_title": "费用包含",
        "extras_title": "额外收费项目",
        "start_point": "阿克套 — 酒店或机场",
        "group_size": "每车 1–3 位客人",
        "vehicle_type": "专业四驱车",

        "groups_label": "团队数量",
        "groups_note": "一个团队 = 一辆车，最多 3 位客人。增加第二队价格翻倍。",
        "group_word": "团",
        "groups_word": "团",
        "up_to_guests": "最多 {n} 位客人",
        "confirm_24h": "24 小时内确认",
        "pay_after": "确认后付款",
        "tour_price_label": "行程价格",

        "your_booking": "您的预订",
        "pick_tour_first": "请选择线路以查看详情。",
        "summary_package": "套餐",
        "summary_route": "路线",
        "summary_groups": "团队",
        "summary_date": "日期",
        "summary_total": "合计",
        "contacts_step": "联系方式",
        "trip_step": "您的行程",
        "not_selected": "未选择",

        "currency_note": "按当前汇率约合",
        "currency": "货币",

        "all_points": "全部地点",
        "map_filter": "显示路线",

        "msg_groups": "团队数量必须在 1 至 {max} 之间。",
        "guests_label": "客人数量",
        "guests_hint": "每车最多 3 人",
        "select_tour_hint": "请从列表中选择",
        "sending": "发送中",
        "sent": "已提交",

        "search_country": "搜索国家",

        "distance": "距离",
        "distance_note": "约",
        "rain_title": "雨天与不可抗力",
        "rain_text": "雨天出于安全考虑，部分地点不开放：图兹拜尔、博克特山和下博兹日拉。"
                     "向导会在当天安排其他景点替代。",
        "rain_short": "雨天关闭",
        "dress_title": "参观清真寺",
        "dress_text": "沙克帕克-阿塔和卡拉曼-阿塔是正在使用的地下清真寺。"
                      "请穿着遮盖肩膀和膝盖的衣物，女士建议佩戴头巾。",
        "dress_short": "需着装得体",

        "group_note": "每组最多 3 位客人。从第 4 位客人起，按行程天数收取附加费。",
        "extra_guests": "额外客人",
        "extra_guest_fee": "额外客人费用",
        "base_price": "行程与套餐",
        "groups": "组数",
        "per_person": "每人",

        "extra_services": "附加服务",
        "extra_services_text": "可选，计入总价。按日计费的服务将按行程天数收取。",
        "per_day": "每天",
        "once": "一次性",
        "services_price": "附加服务",
    },
}

for _lang, _texts in EXTRA_TEXTS.items():
    TRANSLATIONS.setdefault(_lang, {}).update(_texts)

# Қалған тілдерге ағылшын нұсқасын қосамыз (жоқ кілттерді ғана)
for _lang in LANGUAGE_CODES:
    for _key, _value in EXTRA_TEXTS["en"].items():
        TRANSLATIONS.setdefault(_lang, {}).setdefault(_key, _value)


# ---------------------------------------------------------------------------
# ЖОЛ АУЫСТЫРУДЫ БІРІЗДЕНДІРУ
# ---------------------------------------------------------------------------
# Аудармаларда жол ауыстыру үш түрлі жазылып қалған: <br>, \n және
# нағыз жол ауыстыру. Барлығын біріне келтіреміз — сонда шаблондағы
# |nl2br сүзгісі оларды дұрыс <br> тегіне айналдырады.

def _normalize_breaks(value):
    if not isinstance(value, str):
        return value
    return (value
            .replace("<br/>", "\n")
            .replace("<br />", "\n")
            .replace("<br>", "\n")
            .replace("\\n", "\n"))


for _lang_code, _dictionary in TRANSLATIONS.items():
    for _key, _value in list(_dictionary.items()):
        _dictionary[_key] = _normalize_breaks(_value)


class Tr(dict):
    """
    Аудармасы жоқ кілт EN нұсқасына түседі — бет ешқашан бос шықпайды.
    tr.tours, tr["tours"], tr.get("tours", "-") — үшеуі де жұмыс істейді.
    """

    def __init__(self, language):
        merged = dict(TRANSLATIONS["en"])
        merged.update(TRANSLATIONS.get(language, {}))
        super().__init__(merged)
        self.language = language

    def __getattr__(self, item):
        try:
            return self[item]
        except KeyError:
            return ""


# =========================================================
# TEMPLATE HELPERS
# =========================================================
# record_once — blueprint тіркелген сәтте бір рет іске қосылады.
# Сондықтан __init__.py файлын өзгертудің қажеті жоқ.

@site_bp.record_once
def _register_template_helpers(state):

    app = state.app

    app.jinja_env.filters["money"] = money
    app.jinja_env.filters["nl2br"] = nl2br

    app.jinja_env.globals.update(
        LANGUAGES=LANGUAGES,
        COUNTRY_CODES=COUNTRY_CODES,
        PACKAGES=PACKAGES,
        html_lang=html_lang,
        media_url=media_url,
        asset=asset,
        usd_rate=usd_rate,
        package_price=package_price,
        tour_package_price=tour_package_price,
        PACKAGE_PRICES=PACKAGE_PRICES,
        get_package=get_package,
        routes_for=routes_for,
        route_options=route_options,
        included_keys=included_keys,
        OVERVIEW_HIGHLIGHTS=OVERVIEW_HIGHLIGHTS,
        ITINERARY_INTRO=ITINERARY_INTRO,
        INCLUDED_TEXT=INCLUDED_TEXT,
        has_route_choice=has_route_choice,
        route_meta=route_meta,
        L=localize,
        translate_duration=translate_duration,
        price_number=price_number,
        duration_days=duration_days,
        SERVICES=SERVICES,
        MAX_PER_GROUP=MAX_PER_GROUP,
        MAX_GROUPS=MAX_GROUPS,
        MAX_GUESTS=MAX_GUESTS,
        extra_person_price=extra_person_price,
        service_price=service_price,
        services_for=services_for,
        get_service=get_service,
        groups_count=groups_count,
        extra_guests_count=extra_guests_count,
        booking_total=booking_total,
    )

    # flask-wtf орнатылмаған болса, шаблон құламауы үшін
    if "csrf_token" not in app.jinja_env.globals:
        app.jinja_env.globals["csrf_token"] = lambda: ""


@site_bp.app_context_processor
def _inject_site_context():
    """
    Бұрын әр роутта language / tr / settings қайталанып жазылатын.
    Енді бір жерде — барлық шаблонға автоматты түрде беріледі.
    """
    language = session.get("language", DEFAULT_LANGUAGE)

    if language not in LANGUAGE_CODES:
        language = DEFAULT_LANGUAGE

    return {
        "language": language,
        "tr": Tr(language),
        "settings": settings(),
        "now_year": date.today().year,
    }


# =========================================================
# MAIN SITE
# =========================================================

@site_bp.get("/")
def index():

    tours = (
        Tour.query
        .filter_by(active=True)
        .order_by(Tour.sort_order)
        .all()
    )

    # Отзывы из базы — только включённые. Если пусто, шаблон покажет
    # встроенные отзывы, чтобы блок не был пустым.
    try:
        db_reviews = (
            Review.query
            .filter_by(active=True)
            .order_by(Review.created_at.desc())
            .all()
        )
    except Exception:
        db_reviews = []

    return render_template(
        "index.html",
        tours=tours,
        map_data=map_data(tours, session.get("language", DEFAULT_LANGUAGE)),
        gallery=gallery_images(),
        gallery_slots=gallery_slots(),
        db_reviews=db_reviews,
    )


# =========================================================
# FAVICON
# =========================================================
# Браузер ең алдымен сайттың түбіріндегі /favicon.ico файлын сұрайды.
# Бұрын бұл жол жоқ еді — сондықтан қойындыда белгіше шықпайтын.

@site_bp.get("/favicon.ico")
def favicon():
    return send_from_directory(
        current_app.static_folder,
        "favicon.ico",
        mimetype="image/vnd.microsoft.icon",
        max_age=60 * 60 * 24 * 7,
    )


@site_bp.get("/apple-touch-icon.png")
@site_bp.get("/apple-touch-icon-precomposed.png")
def apple_touch_icon():
    return send_from_directory(
        current_app.static_folder,
        "apple-touch-icon.png",
        mimetype="image/png",
        max_age=60 * 60 * 24 * 7,
    )


# =========================================================
# TOUR DETAIL
# =========================================================

@site_bp.get("/tour/<int:id>")
def tour_detail(id):

    tour = db.get_or_404(Tour, id)

    selected_package = request.args.get("package", DEFAULT_PACKAGE)

    if selected_package not in PACKAGE_CODES:
        selected_package = DEFAULT_PACKAGE

    # Бір күндік турда бағыт таңдалады (?route=3)
    try:
        selected_route = int(request.args.get("route") or 0)
    except (TypeError, ValueError):
        selected_route = 0

    return render_template(
        "tour_detail.html",
        tour=tour,
        selected_package=selected_package,
        selected_route=selected_route,
    )


# =========================================================
# BOOKING
# =========================================================

def booking_tours_data(tours, language):
    """
    Брондау бетіндегі тірі карточка үшін тур деректері.
    {тур id: {title, image, duration, days, prices: {basic: ...}}}
    """
    data = {}

    for tour in tours:
        days = duration_days(getattr(tour, "duration", "")) or 1

        prices = {}
        for package in PACKAGES:
            prices[package["code"]] = tour_package_price(tour, package["code"])

        data[str(tour.id)] = {
            "title": getattr(tour, "title", ""),
            "image": media_url(getattr(tour, "image", "")),
            "duration": translate_duration(getattr(tour, "duration", ""), language),
            "days": days,
            "prices": prices,
            "has_routes": bool(route_options(tour)),
        }

    return data


def route_choices(tours):
    """
    {тур id: [{"n": 1, "title": "..."}]} — booking бетіндегі JS
    осы арқылы бағыт тізімін толтырады.
    Тек бір күндік турлар кіреді.
    """
    language = session.get("language", DEFAULT_LANGUAGE)
    data = {}

    for tour in tours:
        options = route_options(tour)
        if options:
            data[str(tour.id)] = [
                {
                    "n": item["n"],
                    "title": localize(item["title"], language),
                    "price": item.get("price") or 0,
                }
                for item in options
            ]

    return data


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[a-zA-Z]{2,}$")

MAX_BOOKING_DAYS = 550          # шамамен 18 ай


@site_bp.route("/booking", methods=["GET", "POST"])
def booking():

    language = session.get("language", DEFAULT_LANGUAGE)

    if language not in LANGUAGE_CODES:
        language = DEFAULT_LANGUAGE

    tr = Tr(language)

    tours = (
        Tour.query
        .filter_by(active=True)
        .order_by(Tour.sort_order)
        .all()
    )

    # -----------------------------------------------------
    # GET — форманы ашу
    # -----------------------------------------------------

    if request.method == "GET":

        # ?tour=3 немесе ?tour=TWO DAY ULTIMATE — екеуі де жұмыс істейді
        raw_tour = (request.args.get("tour") or "").strip()

        preselected = None

        if raw_tour.isdigit():
            preselected = db.session.get(Tour, int(raw_tour))

        if preselected is None and raw_tour:
            preselected = Tour.query.filter_by(title=raw_tour).first()

        selected_package = request.args.get("package", DEFAULT_PACKAGE)

        if selected_package not in PACKAGE_CODES:
            selected_package = DEFAULT_PACKAGE

        try:
            selected_route = int(request.args.get("route") or 0)
        except (TypeError, ValueError):
            selected_route = 0

        return render_template(
            "booking.html",
            tours=tours,
            preselected=preselected,
            selected_package=selected_package,
            selected_route=selected_route,
            selected_services=[],
            route_choices=route_choices(tours),
            tours_data=booking_tours_data(tours, language),
            form_data=None,
        )

    # -----------------------------------------------------
    # HONEYPOT
    # -----------------------------------------------------
    # Боттар бұл өрісті толтырады, адам көрмейді.
    # Ботқа сәтті сияқты көрсетіп, ештеңе сақтамаймыз.

    if request.form.get("website"):
        flash(tr.msg_ok, "success")
        return redirect(url_for("site.booking"))

    form = request.form

    name = (form.get("name") or "").strip()
    email = (form.get("email") or "").strip()
    country_code = (form.get("country_code") or "+7").strip()
    phone_number = (form.get("phone") or "").strip()
    tour_raw = (form.get("tour") or "").strip()
    package = (form.get("package") or DEFAULT_PACKAGE).strip()
    tour_date_text = (form.get("tour_date") or "").strip()
    message = (form.get("message") or "").strip()

    # қосымша қызметтер (checkbox)
    selected_services = [
        code for code in form.getlist("services") if code in SERVICE_CODES
    ]

    try:
        selected_route = int(form.get("route") or 0)
    except (TypeError, ValueError):
        selected_route = 0

    errors = []

    # --- ТУР: базада бар ма? ---------------------------------
    # Бұрын форманың кез келген мәтіні сол күйі сақталатын.

    selected_tour = None

    if tour_raw.isdigit():
        selected_tour = db.session.get(Tour, int(tour_raw))

    if selected_tour is None and tour_raw:
        selected_tour = Tour.query.filter_by(title=tour_raw).first()

    if selected_tour is None:
        errors.append(tr.msg_tour)

    # --- БАҒЫТ (тек бір күндік турда) --------------------------

    route_title = ""
    route_price = 0

    if selected_tour is not None:
        options = route_options(selected_tour)

        if options:
            # Бір күндік тур: бағыт МІНДЕТТІ
            match = [r for r in options if r["n"] == selected_route]

            if not match:
                errors.append(tr.msg_route)
            else:
                route_title = localize(match[0]["title"], language)
                # Бағыттың өз бағасы болса, сол қолданылады
                route_price = match[0].get("price") or 0

            # Бір күндік турда пакет жоқ — әрқашан базалық
            package = DEFAULT_PACKAGE

    # --- ПАКЕТ ------------------------------------------------

    if package not in PACKAGE_CODES:
        errors.append(tr.msg_package)
        package = DEFAULT_PACKAGE

    # --- ҚОСЫМША ҚЫЗМЕТТЕР -----------------------------------
    # Формадан келген белгісіз кодтарды алып тастаймыз

    chosen_services = [
        code for code in form.getlist("services")
        if code in SERVICE_CODES
    ]

    # --- ҚОНАҚ САНЫ -------------------------------------------
    # Бір көлікке 3 адам. 4-ші адамнан екінші көлік қосылады,
    # оның ақысы booking_total() ішінде есептеледі.

    try:
        groups = int(form.get("groups") or 1)
    except (TypeError, ValueError):
        groups = 0

    if not 1 <= groups <= MAX_GROUPS:
        errors.append(tr.msg_groups.replace("{max}", str(MAX_GROUPS)))

    # --- ҚОНАҚ САНЫ -------------------------------------------
    # Топ саны көліктің санын береді, ал қонақ саны нақты адам саны.
    # Бір көлікке 3 адамнан аспауы керек.

    try:
        guests = int(form.get("guests") or 0)
    except (TypeError, ValueError):
        guests = 0

    max_guests = max(groups, 1) * MAX_PER_GROUP

    if guests and not 1 <= guests <= max_guests:
        errors.append(tr.msg_guests.replace("{max}", str(max_guests)))

    # --- КҮН ---------------------------------------------------
    # input min= тек браузерде істейді, сондықтан серверде де тексереміз.

    tour_date = None

    if not tour_date_text:
        errors.append(tr.msg_date)
    else:
        try:
            tour_date = date.fromisoformat(tour_date_text)
        except ValueError:
            errors.append(tr.msg_date_format)
        else:
            if tour_date < date.today():
                errors.append(tr.msg_date_past)
            elif tour_date > date.today() + timedelta(days=MAX_BOOKING_DAYS):
                errors.append(tr.msg_date_far)

    # --- ҚАЛҒАН ӨРІСТЕР ---------------------------------------

    if not name:
        errors.append(tr.msg_name)

    if not phone_number:
        errors.append(tr.msg_phone)

    if not email or not EMAIL_RE.match(email):
        errors.append(tr.msg_email)

    # -----------------------------------------------------
    # ҚАТЕ БОЛСА
    # -----------------------------------------------------
    # Бұрын redirect жасалатын да, пайдаланушы жазғанының бәрі
    # жоғалатын. Енді форма толтырылған күйі қайта көрсетіледі.

    if errors:

        for text in errors:
            flash(text, "error")

        return render_template(
            "booking.html",
            tours=tours,
            preselected=selected_tour,
            selected_package=package,
            selected_route=selected_route,
            selected_services=selected_services,
            route_choices=route_choices(tours),
            tours_data=booking_tours_data(tours, language),
            form_data=form,
        )

    # -----------------------------------------------------
    # САҚТАУ
    # -----------------------------------------------------

    summary = booking_total(
        selected_tour, package, groups, chosen_services,
        unit_price=route_price or None,
    )

    total = summary["total"]

    package_name = get_package(package)["name"]

    # Өтінімнің толық мазмұны — менеджер бәрін бір жерден көреді

    details = ["[{} · {} ₸]".format(package_name, money(total))]

    # Бір күндік турда таңдалған бағыт
    if route_title:
        details.append("{}: {}".format(tr.route_label, route_title))

    if guests:
        details.append("{}: {}".format(tr.guests_label, guests))

    if summary["groups"] > 1:
        details.append("{}: {} × {} ₸".format(
            tr.groups_label, summary["groups"], money(summary["one_group"])
        ))

    # Пакетте бар қызметтерді бөлек жазбаймыз — олар тегін,
    # әйтпесе өтінімде "0 ₸" деген түсініксіз жол шығады.
    paid_services = [
        code for code in chosen_services
        if not is_included(get_service(code) or {}, package)
    ]

    if paid_services:
        names = [
            localize(get_service(code)["name"], language)
            for code in paid_services
        ]
        details.append("{}: {} ({} ₸)".format(
            tr.extra_services, ", ".join(names), money(summary["services"])
        ))

    booking_row = Booking(
        name=name,
        email=email,
        phone="{} {}".format(country_code, phone_number),
        tour=selected_tour.title,
        guests=guests or summary["guests"],
        tour_date=tour_date,
        message=message,
    )

    # Booking моделінде package / total бағаналары бар болса — жазамыз.
    # Жоқ болса, ақпарат жоғалмас үшін message ішіне қосамыз.

    if hasattr(booking_row, "package"):
        booking_row.package = package
    if hasattr(booking_row, "total_price"):
        booking_row.total_price = total
    if hasattr(booking_row, "route"):
        booking_row.route = route_title

    if hasattr(booking_row, "groups"):
        booking_row.groups = summary["groups"]

    if hasattr(booking_row, "services"):
        booking_row.services = ",".join(chosen_services)

    # Модельде арнайы бағаналар жоқ болса, ақпарат жоғалмас үшін
    # бәрін message ішіне жазамыз.

    booking_row.message = (message + "\n\n" + "\n".join(details)).strip()

    db.session.add(booking_row)
    db.session.commit()

    # -----------------------------------------------------
    # TELEGRAM ХАБАРЛАМАСЫ
    # -----------------------------------------------------
    # Фонда жіберіледі: Telegram жауап бермей қалса да, клиент
    # растауды бірден көреді. Хабар жетпесе, өтінім базада қалады.

    if telegram_notify is not None:
        try:
            text, buttons = telegram_notify.booking_message(
                booking_row,
                tour_title=selected_tour.title,
                package_name=package_name,
                total=money(total),
                details=details[1:],          # бірінші жол — баға, ол бөлек тұр
            )
            telegram_notify.notify(text, buttons)
        except Exception:
            current_app.logger.exception("Telegram хабарламасын құру сәтсіз")

    flash(tr.msg_ok, "success")

    return redirect(url_for("site.booking"))


# =========================================================
# ADMIN LOGIN
# =========================================================

def _read_env_file():
    """
    .env файлын өзіміз оқимыз — python-dotenv қажет емес.
    Жобаның түбірінде де, app/ ішінде де іздейді.
    """
    values = {}

    here = os.path.dirname(os.path.abspath(__file__))

    candidates = [
        os.path.join(os.getcwd(), ".env"),
        os.path.join(os.path.dirname(here), ".env"),
        os.path.join(here, ".env"),
    ]

    for path in candidates:
        if not os.path.isfile(path):
            continue

        try:
            with open(path, encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()

                    if not line or line.startswith("#") or "=" not in line:
                        continue

                    key, _, value = line.partition("=")
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")

                    if key and key not in values:
                        values[key] = value
        except OSError:
            continue

        break

    return values


def admin_credentials():
    """
    Логин мен пароль — басымдық реті:
      1) жүйенің айнымалысы (os.environ)
      2) .env файлы
      3) app.config
      4) әдепкі: admin / admin123
    """
    env_file = _read_env_file()

    def pick(key, default):
        return (
            (os.environ.get(key) or "").strip()
            or env_file.get(key, "").strip()
            or str(current_app.config.get(key) or "").strip()
            or default
        )

    return pick("ADMIN_USERNAME", "admin"), pick("ADMIN_PASSWORD", "admin123")


@admin_bp.route("/login", methods=["GET", "POST"])
def login():

    if session.get("admin_logged_in"):
        return redirect(url_for("admin.dashboard"))

    if request.method == "POST":

        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        admin_username, admin_password = admin_credentials()

        # Салыстыру уақыт бойынша бірдей — пароль ұзындығы білінбейді
        import hmac

        ok = (
            hmac.compare_digest(username, admin_username)
            and hmac.compare_digest(password, admin_password)
        )

        if ok:
            session.clear()
            session["admin_logged_in"] = True
            session.permanent = True

            flash("Добро пожаловать в панель управления.", "success")

            return redirect(url_for("admin.dashboard"))

        flash("Неверный логин или пароль.", "error")

    # Әдепкі пароль әлі тұр ма — ескерту көрсетеміз
    using_default = admin_credentials()[1] == "admin123"

    return render_template(
        "admin/login.html",
        using_default=using_default,
    )


# =========================================================
# ADMIN LOGOUT
# =========================================================

@admin_bp.get("/logout")
@login_required
def logout():

    session.pop(
        "admin_logged_in",
        None
    )

    return redirect(
        url_for("admin.login")
    )


# =========================================================
# ADMIN: ОРТАҚ КӨМЕКШІЛЕР
# =========================================================

# Сол жақ мәзір. Бет әлі жасалмаған болса, сілтеме автоматты
# жасырылады — сондықтан тізімге алдын ала жазып қоюға болады.
ADMIN_MENU = [
    ("admin.dashboard", "Главная",  "grid"),
    ("admin.bookings",  "Заявки",  "inbox"),
    ("admin.tours_page", "Туры", "map"),
    ("admin.routes_page", "Маршруты", "route"),
    ("admin.gallery_page", "Галерея", "image"),
    ("admin.reviews",   "Отзывы",   "star"),
    ("admin.settings_page", "Настройки", "gear"),
]


@admin_bp.app_context_processor
def inject_admin_menu():
    """Мәзірді барлық админ бетіне береді."""
    items = []

    for endpoint, label, icon in ADMIN_MENU:
        if endpoint in current_app.view_functions:
            items.append({
                "endpoint": endpoint,
                "label": label,
                "icon": icon,
            })

    return {"admin_menu": items}


def money_kzt(value):
    try:
        return "{:,.0f}".format(float(value or 0)).replace(",", " ")
    except (TypeError, ValueError):
        return "0"


BOOKING_STATUSES = ["Новая", "В работе", "Подтверждена", "Отменена"]


# =========================================================
# ADMIN DASHBOARD
# =========================================================

@admin_bp.get("/")
@login_required
def dashboard():

    from datetime import date, timedelta

    bookings = (
        Booking.query
        .order_by(Booking.created_at.desc())
        .all()
    )

    tours = Tour.query.order_by(Tour.sort_order, Tour.id).all()
    reviews = Review.query.order_by(Review.created_at.desc()).all()
    routes = TourRoute.query.all()

    today = date.today()
    month_start = today.replace(day=1)

    def created_date(item):
        value = getattr(item, "created_at", None)
        return value.date() if value else None

    new_count = len([b for b in bookings if (b.status or "") == "Новая"])

    month_bookings = [
        b for b in bookings
        if created_date(b) and created_date(b) >= month_start
    ]

    month_total = sum(int(getattr(b, "total_price", 0) or 0) for b in month_bookings)

    week_start = today - timedelta(days=6)
    week_count = len([
        b for b in bookings
        if created_date(b) and created_date(b) >= week_start
    ])

    # Алдағы сапарлар — күні әлі өтпегендер
    upcoming = [
        b for b in bookings
        if b.tour_date and b.tour_date >= today
           and (b.status or "") != "Отменена"
    ]
    upcoming.sort(key=lambda b: b.tour_date)

    stats = {
        "new": new_count,
        "week": week_count,
        "month_total": money_kzt(month_total),
        "month_count": len(month_bookings),
        "tours": len([t for t in tours if t.active]),
        "routes": len(routes),
        "reviews": len(reviews),
        "upcoming": len(upcoming),
    }

    return render_template(
        "admin/dashboard.html",
        stats=stats,
        latest=bookings[:6],
        upcoming=upcoming[:5],
        tours=tours,
        money=money_kzt,
    )


# =========================================================
# ADMIN: ӨТІНІМДЕР
# =========================================================

@admin_bp.get("/bookings")
@login_required
def bookings():

    from datetime import date

    status = (request.args.get("status") or "").strip()
    query = (request.args.get("q") or "").strip()

    all_items = (
        Booking.query
        .order_by(Booking.created_at.desc())
        .all()
    )

    items = list(all_items)

    if status:
        items = [b for b in items if (b.status or "Новая") == status]

    if query:
        needle = query.lower()

        def matches(b):
            haystack = " ".join([
                str(b.name or ""), str(b.phone or ""),
                str(b.email or ""), str(b.tour or ""),
            ]).lower()
            return needle in haystack

        items = [b for b in items if matches(b)]

    # Әр статустың саны — сүзгі түймелеріне
    counts = {"": len(all_items)}

    for name in BOOKING_STATUSES:
        counts[name] = len([b for b in all_items if (b.status or "Новая") == name])

    total_sum = money_kzt(
        sum(int(getattr(b, "total_price", 0) or 0) for b in items)
    )

    # Қызмет кодтарын оқылатын атауға айналдырамыз
    language = session.get("language", DEFAULT_LANGUAGE)

    services_map = {
        service["code"]: localize(service["name"], language)
        for service in SERVICES
    }

    return render_template(
        "admin/bookings.html",
        items=items,
        counts=counts,
        statuses=BOOKING_STATUSES,
        current_status=status,
        query=query,
        total_sum=total_sum,
        money=money_kzt,
        services_map=services_map,
        today=date.today(),
        stats={"new": counts.get("Новая", 0)},
    )


@admin_bp.post("/bookings/<int:id>/status")
@login_required
def booking_status(id):
    """Кестедегі тізімнен статусты ауыстыру."""
    item = db.get_or_404(Booking, id)

    value = (request.form.get("status") or "").strip()

    if value in BOOKING_STATUSES:
        item.status = value
        db.session.commit()

    return redirect(request.referrer or url_for("admin.bookings"))


@admin_bp.post("/bookings/<int:id>/note")
@login_required
def booking_note(id):
    """Менеджердің жеке жазбасы — клиентке көрінбейді."""
    item = db.get_or_404(Booking, id)

    if hasattr(item, "admin_note"):
        item.admin_note = (request.form.get("admin_note") or "").strip()
        db.session.commit()
        flash("Заметка сохранена.", "success")

    return redirect(request.referrer or url_for("admin.bookings"))


@admin_bp.post("/bookings/<int:id>/delete")
@login_required
def delete_booking(id):
    item = db.get_or_404(Booking, id)

    db.session.delete(item)
    db.session.commit()

    flash("Заявка удалена.", "success")

    return redirect(url_for("admin.bookings"))


# =========================================================
# ADMIN: СУРЕТ ЖҮКТЕУ
# =========================================================
# Файлды static/<folder>/ ішіне сақтайды да, жолын қайтарады.
# Мысалы: "routes/day2-01.jpg"

UPLOAD_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}

# Видео файлдары — тек баптаулар бетінде
VIDEO_EXTENSIONS = {".mp4", ".webm", ".mov"}

MAX_UPLOAD_BYTES = 8 * 1024 * 1024        # 8 МБ


def _safe_name(name):
    """Файл атын қауіпсіз түрге келтіреді: тек әріп, сан, сызықша."""
    name = os.path.basename(str(name or "")).strip().lower()
    name = re.sub(r"[^a-z0-9._-]+", "-", name)
    return name.strip("-._") or "file"


# ---------------------------------------------------------
# CLOUDINARY
# ---------------------------------------------------------
# .env немесе Render-де CLOUDINARY_URL болса — файлдар бұлтқа
# жүктеледі және ешқашан жоғалмайды. Болмаса — бұрынғыдай static/.

def _cloudinary():
    """Бапталған cloudinary модулін қайтарады, болмаса None."""
    url = (os.environ.get("CLOUDINARY_URL") or "").strip()

    if not url.startswith("cloudinary://"):
        return None

    try:
        import cloudinary
        import cloudinary.uploader
    except ImportError:
        current_app.logger.warning("cloudinary кітапханасы орнатылмаған")
        return None

    # cloudinary://API_KEY:API_SECRET@CLOUD_NAME — өзіміз бөлшектейміз
    try:
        creds, cloud_name = url[len("cloudinary://"):].rsplit("@", 1)
        api_key, api_secret = creds.split(":", 1)
    except ValueError:
        current_app.logger.warning("CLOUDINARY_URL пішімі қате")
        return None

    cloudinary.config(
        cloud_name=cloud_name.strip(),
        api_key=api_key.strip(),
        api_secret=api_secret.strip(),
        secure=True,
    )

    return cloudinary


def cloud_enabled():
    return _cloudinary() is not None


def _cloud_upload(file_storage, folder, is_video):
    """
    Файлды Cloudinary-ге жүктейді.
    Қайтарады: (сілтеме, public_id) немесе ("", "") қате болса.
    """
    cloud = _cloudinary()
    if cloud is None:
        return "", ""

    try:
        result = cloud.uploader.upload(
            file_storage.stream,
            folder="mangystau/" + (folder or "uploads").strip("/"),
            resource_type="video" if is_video else "image",
            use_filename=True,
            unique_filename=True,
            overwrite=False,
        )
    except Exception:
        current_app.logger.exception("Cloudinary-ге жүктеу сәтсіз")
        flash("Не удалось загрузить файл в облако.", "error")
        return "", ""

    url = result.get("secure_url", "")

    # Суреттерді браузерге қарай өзі сығып, форматын таңдайды:
    # WebP/AVIF, сапасы автоматты — бет әлдеқайда жылдам ашылады
    if url and not is_video and "/upload/" in url:
        url = url.replace("/upload/", "/upload/f_auto,q_auto/", 1)

    return url, result.get("public_id", "")


def cloud_delete(public_id, is_video=False):
    """Cloudinary-ден жояды. Қате болса — үнсіз өтеді."""
    cloud = _cloudinary()

    if cloud is None or not public_id:
        return

    try:
        cloud.uploader.destroy(
            public_id,
            resource_type="video" if is_video else "image",
        )
    except Exception:
        current_app.logger.exception("Cloudinary-ден жою сәтсіз")


LAST_PUBLIC_ID = {"value": ""}


def save_upload(file_storage, folder="uploads", prefix="", allow_video=False):
    """
    Жүктелген файлды сақтайды.

    Қайтарады: "routes/day2-01.jpg" немесе бос жол (файл жоқ/жарамсыз).
    Бір атты файл болса, соңына сан қосылады — ескісі жоғалмайды.
    """
    if not file_storage or not getattr(file_storage, "filename", ""):
        return ""

    name = _safe_name(file_storage.filename)
    base, ext = os.path.splitext(name)

    allowed = set(UPLOAD_EXTENSIONS)

    if allow_video:
        allowed |= VIDEO_EXTENSIONS

    if ext.lower() not in allowed:
        flash("Этот тип файла не поддерживается: {}".format(ext), "error")
        return ""

    # --- Бұлт қосулы болса — сонда жүктейміз ---
    LAST_PUBLIC_ID["value"] = ""

    if cloud_enabled():
        url, public_id = _cloud_upload(
            file_storage,
            folder=folder,
            is_video=ext.lower() in VIDEO_EXTENSIONS,
        )
        LAST_PUBLIC_ID["value"] = public_id
        return url

    if prefix:
        base = "{}-{}".format(_safe_name(prefix), base)

    folder_path = os.path.join(current_app.static_folder, folder)
    os.makedirs(folder_path, exist_ok=True)

    final = base + ext.lower()
    counter = 2

    while os.path.exists(os.path.join(folder_path, final)):
        final = "{}-{}{}".format(base, counter, ext.lower())
        counter += 1

    path = os.path.join(folder_path, final)

    try:
        file_storage.save(path)
    except Exception:
        current_app.logger.exception("Файлды сақтау сәтсіз")
        flash("Не удалось сохранить файл.", "error")
        return ""

    # Тым үлкен файлды қабылдамаймыз
    limit = MAX_UPLOAD_BYTES * 8 if ext.lower() in VIDEO_EXTENSIONS else MAX_UPLOAD_BYTES

    if os.path.getsize(path) > limit:
        os.remove(path)
        flash("Файл слишком большой (не более {} МБ).".format(limit // (1024 * 1024)), "error")
        return ""

    return "{}/{}".format(folder, final)


# =========================================================
# ADMIN: МАРШРУТТАР
# =========================================================

@admin_bp.get("/routes")
@login_required
def routes_page():

    tour_id = (request.args.get("tour") or "").strip()

    tours = Tour.query.order_by(Tour.sort_order, Tour.id).all()

    query = TourRoute.query

    if tour_id.isdigit():
        query = query.filter_by(tour_id=int(tour_id))

    items = query.order_by(
        TourRoute.tour_id,
        TourRoute.day_number,
        TourRoute.sort_order,
    ).all()

    # Тур бойынша топтаймыз
    groups = []

    for tour in tours:
        tour_routes = [r for r in items if r.tour_id == tour.id]

        if tour_routes or not tour_id:
            groups.append({"tour": tour, "routes": tour_routes})

    counts = {t.id: len([r for r in TourRoute.query.all() if r.tour_id == t.id])
              for t in tours}

    return render_template(
        "admin/routes.html",
        groups=groups,
        tours=tours,
        counts=counts,
        current_tour=tour_id,
        total=len(TourRoute.query.all()),
    )


def _route_form_data(item=None):
    """Формадағы мәндерді оқиды."""
    form = request.form

    try:
        day_number = int(form.get("day_number") or 1)
    except ValueError:
        day_number = 1

    try:
        sort_order = int(form.get("sort_order") or 0)
    except ValueError:
        sort_order = 0

    try:
        km = int(re.sub(r"[^\d]", "", form.get("km") or "0") or 0)
    except ValueError:
        km = 0

    return {
        "tour_id": int(form.get("tour_id") or 0),
        "day_number": day_number,
        "sort_order": sort_order,
        "km": km,
        "title": (form.get("title") or "").strip(),
        "description": (form.get("description") or "").strip(),
        "note": (form.get("note") or "").strip(),
        "duration": (form.get("duration") or "").strip(),
        "vehicle": (form.get("vehicle") or "").strip(),
        "group_size": (form.get("group_size") or "").strip(),
        "price": (form.get("price") or "").strip(),
        "active": "active" in form,
    }


@admin_bp.route("/routes/new", methods=["GET", "POST"])
@login_required
def new_route():

    tours = Tour.query.order_by(Tour.sort_order, Tour.id).all()

    if request.method == "POST":
        data = _route_form_data()

        if not data["title"] or not data["tour_id"]:
            flash("Укажите тур и название.", "error")
            return render_template("admin/route_form.html", route=None, tours=tours)

        item = TourRoute(**data)

        # Сурет: жүктелген файл немесе қолмен жазылған жол
        uploaded = save_upload(
            request.files.get("image_file"),
            folder="routes",
            prefix="day{}".format(data["day_number"]),
        )

        item.image = uploaded or (request.form.get("image") or "").strip()

        db.session.add(item)
        db.session.commit()

        flash("Маршрут добавлен.", "success")

        return redirect(url_for("admin.routes_page", tour=data["tour_id"]))

    return render_template("admin/route_form.html", route=None, tours=tours)


@admin_bp.route("/routes/<int:id>/edit", methods=["GET", "POST"])
@login_required
def edit_route(id):

    item = db.get_or_404(TourRoute, id)
    tours = Tour.query.order_by(Tour.sort_order, Tour.id).all()

    if request.method == "POST":
        data = _route_form_data(item)

        if not data["title"] or not data["tour_id"]:
            flash("Укажите тур и название.", "error")
            return render_template("admin/route_form.html", route=item, tours=tours)

        for field, value in data.items():
            setattr(item, field, value)

        uploaded = save_upload(
            request.files.get("image_file"),
            folder="routes",
            prefix="day{}".format(data["day_number"]),
        )

        if uploaded:
            item.image = uploaded
        elif "image" in request.form:
            item.image = (request.form.get("image") or "").strip()

        db.session.commit()

        flash("Маршрут обновлён.", "success")

        return redirect(url_for("admin.routes_page", tour=item.tour_id))

    return render_template("admin/route_form.html", route=item, tours=tours)


@admin_bp.post("/routes/<int:id>/delete")
@login_required
def delete_route(id):
    item = db.get_or_404(TourRoute, id)
    tour_id = item.tour_id

    db.session.delete(item)
    db.session.commit()

    flash("Маршрут удалён.", "success")

    return redirect(url_for("admin.routes_page", tour=tour_id))


@admin_bp.post("/routes/<int:id>/move")
@login_required
def move_route(id):
    """Маршруттың ретін жоғары-төмен жылжыту."""
    item = db.get_or_404(TourRoute, id)

    step = -1 if request.form.get("dir") == "up" else 1

    item.sort_order = (item.sort_order or 0) + step
    db.session.commit()

    return redirect(url_for("admin.routes_page", tour=item.tour_id))


# =========================================================
# ADMIN: ГАЛЕРЕЯ (три отдельных блока)
# =========================================================

SLOT_TITLES = {
    1: "Блок 1 — большой, слева",
    2: "Блок 2 — справа сверху",
    3: "Блок 3 — справа снизу",
}


@admin_bp.get("/gallery")
@login_required
def gallery_page():

    use_db = gallery_uses_db()

    slots = []

    for n in range(1, GALLERY_SLOTS + 1):
        slots.append({
            "n": n,
            "title": SLOT_TITLES.get(n, "Блок {}".format(n)),
            "images": db_slot_images(n) if use_db else slot_images(n),
        })

    # Бумадағы суреттер — бұлтқа көшіруге болады
    folder_count = sum(len(slot_images(n)) for n in range(1, GALLERY_SLOTS + 1))

    return render_template(
        "admin/gallery.html",
        slots=slots,
        use_db=use_db,
        cloud=cloud_enabled(),
        folder_count=folder_count,
        legacy=[] if use_db else gallery_images(limit=100),
        using_fallback=not use_db and not any(s["images"] for s in slots),
    )


@admin_bp.post("/gallery/<int:slot>/upload")
@login_required
def gallery_upload(slot):
    """Бір блокқа бірден бірнеше сурет."""
    if slot not in range(1, GALLERY_SLOTS + 1):
        abort(404)

    files = [f for f in request.files.getlist("photos") if f and f.filename]

    if not files:
        flash("Выберите хотя бы одно фото.", "error")
        return redirect(url_for("admin.gallery_page"))

    # Бұлт қосулы болса — базаға жазамыз, әйтпесе бұрынғыдай бумаға
    if cloud_enabled() and GalleryImage is not None:
        start = (
            db.session.query(db.func.max(GalleryImage.sort_order))
            .filter_by(slot=slot).scalar() or 0
        )
        saved = 0

        for index, file in enumerate(files, start=1):
            url = save_upload(file, folder="gallery/{}".format(slot))
            if url:
                db.session.add(GalleryImage(
                    slot=slot,
                    url=url,
                    public_id=LAST_PUBLIC_ID["value"],
                    sort_order=start + index,
                ))
                saved += 1

        db.session.commit()
    else:
        import time
        stamp = time.strftime("%Y%m%d%H%M%S")
        saved = 0
        for index, file in enumerate(files, start=1):
            if save_upload(file, folder="gallery/{}".format(slot),
                           prefix="{}-{:02d}".format(stamp, index)):
                saved += 1

    if saved:
        flash("Загружено фото: {} — в блок {}.".format(saved, slot), "success")

    return redirect(url_for("admin.gallery_page") + "#slot-{}".format(slot))


def _gallery_file(slot, name):
    """Бумадағы файлдың қауіпсіз жолы."""
    safe = os.path.basename(name or "")
    if not safe or slot not in range(1, GALLERY_SLOTS + 1):
        return None
    path = os.path.join(_slot_folder(slot), safe)
    return path if os.path.isfile(path) else None


@admin_bp.post("/gallery/<int:slot>/delete")
@login_required
def gallery_delete(slot):
    image_id = request.form.get("id")

    if image_id and GalleryImage is not None:
        row = db.session.get(GalleryImage, int(image_id))
        if row:
            cloud_delete(row.public_id)
            db.session.delete(row)
            db.session.commit()
            flash("Фото удалено.", "success")
    else:
        path = _gallery_file(slot, request.form.get("name"))
        if path:
            os.remove(path)
            flash("Фото удалено.", "success")

    return redirect(url_for("admin.gallery_page") + "#slot-{}".format(slot))


@admin_bp.post("/gallery/<int:slot>/move")
@login_required
def gallery_move(slot):
    try:
        target = int(request.form.get("to") or 0)
    except ValueError:
        target = 0

    if target not in range(1, GALLERY_SLOTS + 1) or target == slot:
        return redirect(url_for("admin.gallery_page"))

    image_id = request.form.get("id")

    if image_id and GalleryImage is not None:
        row = db.session.get(GalleryImage, int(image_id))
        if row:
            row.slot = target
            db.session.commit()
    else:
        path = _gallery_file(slot, request.form.get("name"))
        if path:
            folder = _slot_folder(target)
            os.makedirs(folder, exist_ok=True)
            os.replace(path, os.path.join(folder, os.path.basename(path)))

    flash("Фото перенесено в блок {}.".format(target), "success")
    return redirect(url_for("admin.gallery_page") + "#slot-{}".format(target))


@admin_bp.post("/gallery/to-cloud")
@login_required
def gallery_to_cloud():
    """
    static/gallery/1, /2, /3 бумаларындағы суреттерді Cloudinary-ге
    көшіреді және базаға жазады. Бір рет басу жеткілікті.
    """
    if not cloud_enabled() or GalleryImage is None:
        flash("Облако не настроено: добавьте CLOUDINARY_URL.", "error")
        return redirect(url_for("admin.gallery_page"))

    cloud = _cloudinary()
    moved = 0

    for n in range(1, GALLERY_SLOTS + 1):
        for index, img in enumerate(slot_images(n), start=1):
            path = os.path.join(_slot_folder(n), img["name"])
            try:
                result = cloud.uploader.upload(
                    path,
                    folder="mangystau/gallery/{}".format(n),
                    resource_type="image",
                    use_filename=True,
                    unique_filename=True,
                )
            except Exception:
                current_app.logger.exception("Көшіру сәтсіз: %s", path)
                continue

            url = result.get("secure_url", "").replace("/upload/", "/upload/f_auto,q_auto/", 1)

            db.session.add(GalleryImage(
                slot=n,
                url=url,
                public_id=result.get("public_id", ""),
                sort_order=index,
            ))
            moved += 1

    db.session.commit()

    if moved:
        flash("Перенесено в облако: {} фото. Теперь галерея хранится там.".format(moved), "success")
    else:
        flash("Нечего переносить.", "error")

    return redirect(url_for("admin.gallery_page"))


@admin_bp.post("/gallery/legacy/assign")
@login_required
def gallery_assign_legacy():
    """Жалпы static/gallery/ суретін блокқа қосу (тек бума режимінде)."""
    name = os.path.basename(request.form.get("name") or "")

    try:
        target = int(request.form.get("to") or 0)
    except ValueError:
        target = 0

    source = os.path.join(current_app.static_folder, "gallery", name)

    if name and os.path.isfile(source) and target in range(1, GALLERY_SLOTS + 1):
        folder = _slot_folder(target)
        os.makedirs(folder, exist_ok=True)

        import shutil
        shutil.copy2(source, os.path.join(folder, name))

        flash("Фото добавлено в блок {}.".format(target), "success")

    return redirect(url_for("admin.gallery_page"))


# =========================================================
# ADMIN: ОТЗЫВЫ
# =========================================================

def _review_form_data():
    """Формадан отзыв деректерін оқиды."""
    form = request.form

    try:
        rating = int(form.get("rating") or 5)
    except ValueError:
        rating = 5

    rating = max(1, min(rating, 5))

    return {
        "name": (form.get("name") or "").strip(),
        "country": (form.get("country") or "").strip(),
        "text": (form.get("text") or "").strip(),
        "tour": (form.get("tour") or "").strip(),
        "rating": rating,
        "active": "active" in form,
    }


def _apply_review(item, data):
    """Модельде бар өрістерге ғана жазамыз — ескі база да бұзылмайды."""
    for field, value in data.items():
        if hasattr(item, field) or field in ("name", "text", "rating", "active"):
            setattr(item, field, value)


@admin_bp.get("/reviews")
@login_required
def reviews():

    show = (request.args.get("show") or "").strip()

    items = (
        Review.query
        .order_by(Review.created_at.desc())
        .all()
    )

    all_count = len(items)
    active_count = len([r for r in items if r.active])

    if show == "active":
        items = [r for r in items if r.active]
    elif show == "hidden":
        items = [r for r in items if not r.active]

    ratings = [int(r.rating or 0) for r in Review.query.all() if r.rating]
    average = round(sum(ratings) / len(ratings), 1) if ratings else 0

    return render_template(
        "admin/reviews.html",
        items=items,
        show=show,
        counts={
            "all": all_count,
            "active": active_count,
            "hidden": all_count - active_count,
        },
        average=average,
    )


@admin_bp.route("/reviews/new", methods=["GET", "POST"])
@login_required
def new_review():

    tours = Tour.query.order_by(Tour.sort_order, Tour.id).all()

    if request.method == "POST":
        data = _review_form_data()

        if not data["name"] or not data["text"]:
            flash("Укажите имя и текст отзыва.", "error")
            return render_template("admin/review_form.html", review=None, tours=tours)

        item = Review(name=data["name"], text=data["text"],
                      rating=data["rating"], active=data["active"])

        _apply_review(item, data)

        photo = save_upload(request.files.get("photo_file"), folder="reviews")

        if hasattr(item, "photo"):
            item.photo = photo or (request.form.get("photo") or "").strip()

        db.session.add(item)
        db.session.commit()

        flash("Отзыв добавлен.", "success")

        return redirect(url_for("admin.reviews"))

    return render_template("admin/review_form.html", review=None, tours=tours)


@admin_bp.route("/reviews/<int:id>/edit", methods=["GET", "POST"])
@login_required
def edit_review(id):

    item = db.get_or_404(Review, id)
    tours = Tour.query.order_by(Tour.sort_order, Tour.id).all()

    if request.method == "POST":
        data = _review_form_data()

        if not data["name"] or not data["text"]:
            flash("Укажите имя и текст отзыва.", "error")
            return render_template("admin/review_form.html", review=item, tours=tours)

        _apply_review(item, data)

        photo = save_upload(request.files.get("photo_file"), folder="reviews")

        if hasattr(item, "photo"):
            if photo:
                item.photo = photo
            elif "photo" in request.form:
                item.photo = (request.form.get("photo") or "").strip()

        db.session.commit()

        flash("Отзыв обновлён.", "success")

        return redirect(url_for("admin.reviews"))

    return render_template("admin/review_form.html", review=item, tours=tours)


@admin_bp.post("/reviews/<int:id>/toggle")
@login_required
def toggle_review(id):
    """Показать / скрыть отзыв одним нажатием."""
    item = db.get_or_404(Review, id)

    item.active = not item.active
    db.session.commit()

    return redirect(request.referrer or url_for("admin.reviews"))


@admin_bp.post("/reviews/<int:id>/delete")
@login_required
def delete_review(id):

    item = db.get_or_404(Review, id)

    db.session.delete(item)
    db.session.commit()

    flash("Отзыв удалён.", "success")

    return redirect(url_for("admin.reviews"))


# =========================================================
# ADMIN: ТУРЫ
# =========================================================

def _int_money(value):
    """'295 000 ₸' → 295000; пусто → 0"""
    digits = re.sub(r"[^\d]", "", str(value or ""))
    return int(digits) if digits else 0


def _tour_form_data():
    form = request.form

    try:
        sort_order = int(form.get("sort_order") or 0)
    except ValueError:
        sort_order = 0

    return {
        "title": (form.get("title") or "").strip(),
        "duration": (form.get("duration") or "").strip(),
        "price": (form.get("price") or "").strip(),
        "description": (form.get("description") or "").strip(),
        "badge": (form.get("badge") or "").strip(),
        "code": (form.get("code") or "").strip(),
        "sort_order": sort_order,
        "active": "active" in form,
        "price_basic": _int_money(form.get("price_basic")),
        "price_plus": _int_money(form.get("price_plus")),
        "price_deluxe": _int_money(form.get("price_deluxe")),
    }


def _apply_tour(item, data):
    """Пишем только в поля, которые есть в модели — старая база не сломается."""
    for field, value in data.items():
        if hasattr(item, field) or field in ("title", "duration", "price",
                                             "description", "badge",
                                             "sort_order", "active"):
            setattr(item, field, value)


def _tour_view(tour):
    """Данные для карточки тура в списке."""
    days = duration_days(tour.duration or "")
    prices = {p["code"]: tour_package_price(tour, p["code"]) for p in PACKAGES}

    custom = any(int(getattr(tour, "price_" + code, 0) or 0) > 0
                 for code in ("basic", "plus", "deluxe"))

    return {
        "tour": tour,
        "days": days,
        "prices": prices,
        "custom_prices": custom,
        "routes": TourRoute.query.filter_by(tour_id=tour.id).count(),
        "one_day": days == 1,
    }


@admin_bp.get("/tours")
@login_required
def tours_page():

    tours = Tour.query.order_by(Tour.sort_order, Tour.id).all()

    return render_template(
        "admin/tours.html",
        items=[_tour_view(t) for t in tours],
        packages=PACKAGES,
        money=money_kzt,
    )


@admin_bp.route("/tours/new", methods=["GET", "POST"])
@login_required
def new_tour():

    if request.method == "POST":
        data = _tour_form_data()

        if not data["title"]:
            flash("Укажите название тура.", "error")
            return render_template("admin/tour_form.html", tour=None,
                                   packages=PACKAGES, defaults={})

        item = Tour(title=data["title"])
        _apply_tour(item, data)

        image = save_upload(request.files.get("image_file"), folder="tours")
        item.image = image or (request.form.get("image") or "").strip()

        db.session.add(item)
        db.session.commit()

        flash("Тур добавлен.", "success")

        return redirect(url_for("admin.tours_page"))

    return render_template("admin/tour_form.html", tour=None,
                           packages=PACKAGES, defaults={})


@admin_bp.route("/tours/<int:id>/edit", methods=["GET", "POST"])
@login_required
def edit_tour(id):

    item = db.get_or_404(Tour, id)

    if request.method == "POST":
        data = _tour_form_data()

        if not data["title"]:
            flash("Укажите название тура.", "error")
        else:
            _apply_tour(item, data)

            image = save_upload(request.files.get("image_file"), folder="tours")

            if image:
                item.image = image
            elif "image" in request.form:
                item.image = (request.form.get("image") or "").strip()

            db.session.commit()

            flash("Тур обновлён.", "success")

            return redirect(url_for("admin.tours_page"))

    # Цены из кода — подсказка, какие цены стоят сейчас, если поле пустое
    days = duration_days(item.duration or "")
    defaults = PACKAGE_PRICES.get(days, {})

    return render_template("admin/tour_form.html", tour=item,
                           packages=PACKAGES, defaults=defaults)


@admin_bp.post("/tours/<int:id>/toggle")
@login_required
def toggle_tour(id):
    item = db.get_or_404(Tour, id)
    item.active = not item.active
    db.session.commit()
    return redirect(request.referrer or url_for("admin.tours_page"))


@admin_bp.post("/tours/<int:id>/move")
@login_required
def move_tour(id):
    """Поменять местами с соседним туром."""
    tours = Tour.query.order_by(Tour.sort_order, Tour.id).all()

    # сначала пронумеруем по порядку — чтобы не было одинаковых номеров
    for index, tour in enumerate(tours):
        tour.sort_order = index

    position = next((i for i, t in enumerate(tours) if t.id == id), None)

    if position is not None:
        step = -1 if request.form.get("dir") == "up" else 1
        other = position + step

        if 0 <= other < len(tours):
            tours[position].sort_order, tours[other].sort_order = other, position

    db.session.commit()
    return redirect(url_for("admin.tours_page"))


@admin_bp.post("/tours/<int:id>/delete")
@login_required
def delete_tour(id):
    item = db.get_or_404(Tour, id)

    db.session.delete(item)
    db.session.commit()

    flash("Тур удалён вместе с его маршрутами.", "success")

    return redirect(url_for("admin.tours_page"))


# =========================================================
# ADMIN: БАПТАУЛАР
# =========================================================
# Әр өріс түсіндірмесімен бір бетте. Сурет пен видеоны
# қолмен көшірмей, бірден жүктеуге болады.

SETTING_FIELDS = [
    {
        "group": "Бренд",
        "items": [
            {"key": "brand_name",     "label": "Название",
             "hint": "Показывается в шапке и подвале сайта", "type": "text"},
            {"key": "brand_subtitle", "label": "Подзаголовок",
             "hint": "Жёлтая надпись под логотипом", "type": "text"},
            {"key": "logo",           "label": "Логотип",
             "hint": "Значок в шапке. Лучше PNG с прозрачным фоном",
             "type": "image", "folder": "", "preview": True},
        ],
    },
    {
        "group": "Главная страница",
        "items": [
            {"key": "hero_video",  "label": "Видео",
             "hint": "Видео в верхней части главной страницы (MP4)", "type": "video"},
            {"key": "hero_poster", "label": "Обложка видео",
             "hint": "Показывается, пока грузится видео. Если пусто — тёмный фон",
             "type": "image", "folder": "", "preview": True},
            {"key": "hero_image",  "label": "Картинка для ссылок",
             "hint": "Показывается, когда ссылку на сайт отправляют в WhatsApp",
             "type": "image", "folder": "", "preview": True},
        ],
    },
    {
        "group": "Контакты",
        "items": [
            {"key": "whatsapp",  "label": "Номер WhatsApp",
             "hint": "Только цифры: 77001234567", "type": "text"},
            {"key": "phone",     "label": "Телефон",
             "hint": "Номер для показа на сайте: +7 700 123 45 67", "type": "text"},
            {"key": "instagram", "label": "Instagram",
             "hint": "Только имя аккаунта, без ссылки: mangystau.tour", "type": "text"},
        ],
    },
    {
        "group": "Цены",
        "items": [
            {"key": "usd_rate", "label": "Курс доллара",
             "hint": "Сколько тенге за 1 доллар. Переключатель ₸ / $ берёт это число",
             "type": "text"},
        ],
    },
]


def _setting_keys():
    keys = []
    for group in SETTING_FIELDS:
        for item in group["items"]:
            keys.append(item["key"])
    return keys


@admin_bp.get("/settings")
@login_required
def settings_page():

    values = settings()

    return render_template(
        "admin/settings.html",
        groups=SETTING_FIELDS,
        values=values,
        usd_rate=usd_rate(),
    )


@admin_bp.post("/settings")
@login_required
def update_settings():

    for key in _setting_keys():

        row = SiteSetting.query.filter_by(key=key).first()

        value = (request.form.get(key) or "").strip()

        # --- файл жүктелген болса, ол басым ---
        uploaded = save_upload(
            request.files.get(key + "_file"),
            folder="",
            prefix="",
            allow_video=True,
        )

        if uploaded:
            value = uploaded

        if row:
            row.value = value
        else:
            db.session.add(SiteSetting(key=key, value=value))

    db.session.commit()

    flash("Настройки сохранены.", "success")

    return redirect(url_for("admin.settings_page"))


# =========================================================
# ADMIN BOOKING STATUS
# =========================================================

@admin_bp.post(
    "/bookings/<int:id>/status"
)
@login_required
def status(id):

    b = db.get_or_404(
        Booking,
        id
    )

    b.status = request.form.get(
        "status",
        "Новая"
    )

    db.session.commit()

    return redirect(
        url_for("admin.dashboard")
    )