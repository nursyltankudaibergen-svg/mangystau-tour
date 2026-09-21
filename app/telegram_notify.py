# -*- coding: utf-8 -*-
"""
Telegram хабарламасы.

Клиент өтінім жібергенде, саған Telegram-ға хабар келеді.

БАПТАУ (.env файлында):

    TELEGRAM_TOKEN=8123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw
    TELEGRAM_CHAT_ID=940346478

Екеуі де жоқ болса, модуль үнсіз тұрады — сайт қалыпты жұмыс істей береді.

МАҢЫЗДЫ: хабарлама жіберілмей қалса да (интернет үзілді, токен қате),
өтінім дерекқорда сақталады. Клиент ештеңе жоғалтпайды.
"""

import json
import logging
import os
import threading
import urllib.parse
import urllib.request

log = logging.getLogger(__name__)

API_URL = "https://api.telegram.org/bot{token}/sendMessage"

TIMEOUT = 8          # секунд


def _read_env_file():
    """
    .env файлын өзіміз оқимыз.

    Flask .env-ті автоматты оқымайды, ал python-dotenv орнатылмаған
    болуы мүмкін. Сондықтан файлды қолмен қараймыз — қосымша
    кітапхананың қажеті жоқ.
    """
    values = {}

    here = os.path.dirname(os.path.abspath(__file__))

    # app/ ішінде де, жоба түбірінде де іздейміз
    candidates = [
        os.path.join(here, ".env"),
        os.path.join(os.path.dirname(here), ".env"),
        os.path.join(os.path.dirname(os.path.dirname(here)), ".env"),
        os.path.join(os.getcwd(), ".env"),
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


_env_cache = None


def _config():
    global _env_cache

    token = (os.environ.get("TELEGRAM_TOKEN") or "").strip()
    chat_id = (os.environ.get("TELEGRAM_CHAT_ID") or "").strip()

    if not token or not chat_id:
        if _env_cache is None:
            _env_cache = _read_env_file()

        token = token or _env_cache.get("TELEGRAM_TOKEN", "").strip()
        chat_id = chat_id or _env_cache.get("TELEGRAM_CHAT_ID", "").strip()

    return token, chat_id


def is_enabled():
    token, chat_id = _config()
    return bool(token and chat_id)


def _escape(text):
    """Telegram HTML режимінде < > & таңбалары экрандалуы керек."""
    return (str(text or "")
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;"))


def _send(text, buttons=None):
    """Нақты жіберу. Бөлек ағында шақырылады."""
    token, chat_id = _config()

    if not token or not chat_id:
        return

    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }

    if buttons:
        payload["reply_markup"] = json.dumps({"inline_keyboard": buttons})

    data = urllib.parse.urlencode(payload).encode("utf-8")

    try:
        request = urllib.request.Request(
            API_URL.format(token=token),
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            result = json.loads(response.read().decode("utf-8"))

            if not result.get("ok"):
                log.warning("Telegram қабылдамады: %s", result.get("description"))

    except Exception as error:
        # Хабарлама жіберілмесе де, өтінім базада сақталған —
        # сондықтан қатені тек логқа жазамыз.
        log.warning("Telegram хабарламасы жіберілмеді: %s", error)


_warned = False


def notify(text, buttons=None):
    """
    Хабарламаны ФОНДА жібереді.

    Неге фонда: Telegram жауап бермей қалса, клиент "жіберу" түймесін
    басып, 8 секунд күтіп отырар еді. Ал фонда жіберсек, клиентке
    растау бірден шығады.
    """
    global _warned

    if not is_enabled():
        if not _warned:
            _warned = True
            log.warning(
                "Telegram бапталмаған: TELEGRAM_TOKEN немесе "
                "TELEGRAM_CHAT_ID табылмады (.env тексеріңіз)"
            )
        return

    thread = threading.Thread(target=_send, args=(text, buttons), daemon=True)
    thread.start()


def booking_message(booking, tour_title, package_name, total, details=None,
                    whatsapp=None):
    """
    Өтінімнің мәтінін құрайды.

    booking — Booking объектісі
    details — қосымша жолдар тізімі (бағыт, топ саны, қызметтер)
    """
    lines = [
        "🔔 <b>ЖАҢА ӨТІНІМ</b>",
        "",
        "👤 <b>{}</b>".format(_escape(getattr(booking, "name", ""))),
    ]

    phone = getattr(booking, "phone", "")
    if phone:
        lines.append("📞 {}".format(_escape(phone)))

    email = getattr(booking, "email", "")
    if email:
        lines.append("✉️ {}".format(_escape(email)))

    lines.append("")
    lines.append("🏜 <b>{}</b>".format(_escape(tour_title)))

    if package_name:
        lines.append("📦 {}".format(_escape(package_name)))

    date = getattr(booking, "tour_date", None)
    if date:
        lines.append("📅 {}".format(date.strftime("%d.%m.%Y")))

    for line in (details or []):
        clean = str(line).strip()
        if clean and not clean.startswith("["):
            lines.append("• {}".format(_escape(clean)))

    if total:
        lines.append("")
        lines.append("💰 <b>{} ₸</b>".format(_escape(total)))

    message = getattr(booking, "message", "")
    if message:
        short = message.split("\n")[0][:300]
        if short:
            lines.append("")
            lines.append("💬 {}".format(_escape(short)))

    buttons = []

    # WhatsApp-қа бірден жазу түймесі
    digits = "".join(ch for ch in str(phone) if ch.isdigit())

    if digits:
        buttons.append([{
            "text": "💬 WhatsApp-қа жазу",
            "url": "https://wa.me/{}".format(digits),
        }])

    return "\n".join(lines), (buttons or None)