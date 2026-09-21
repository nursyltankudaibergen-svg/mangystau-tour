import os
from pathlib import Path

from flask import Flask
from markupsafe import Markup, escape
from flask_sqlalchemy import SQLAlchemy


db = SQLAlchemy()


# ==============================
# .ENV ФАЙЛЫН ОҚУ
# ==============================
# python-dotenv қажет емес. Жүйеде (Render) бұрыннан орнатылған
# айнымалы басым — .env тек компьютерде толтырады.

def _load_env_file():
    root = Path(__file__).resolve().parent.parent

    for path in (root / ".env", Path.cwd() / ".env"):
        if not path.is_file():
            continue

        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()

            if not line or line.startswith("#") or "=" not in line:
                continue

            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")

            if key and key not in os.environ:
                os.environ[key] = value

        break


# ==============================
# ДЕРЕКҚОР МЕКЕНЖАЙЫ
# ==============================
# DATABASE_URL болса — Neon (Postgres), болмаса — жергілікті SQLite.

def _database_uri(instance_path):
    url = (os.getenv("DATABASE_URL") or "").strip()

    if not url:
        return "sqlite:///" + str(Path(instance_path) / "mangystau.sqlite3")

    # Кейбір сервистер "postgres://" береді — SQLAlchemy "postgresql://" күтеді
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]

    return _with_driver(url)


def _with_driver(url):
    """
    Postgres драйверін таңдайды: psycopg2 немесе жаңа psycopg (3-нұсқа).
    Python 3.14 сияқты жаңа нұсқаларда psycopg2 орнатылмауы мүмкін —
    сонда psycopg-ке өзі ауысады.
    """
    if not url.startswith("postgresql://"):
        return url

    try:
        import psycopg2  # noqa: F401
        return url
    except ImportError:
        pass

    try:
        import psycopg  # noqa: F401
        return "postgresql+psycopg://" + url[len("postgresql://"):]
    except ImportError:
        return url


def create_app():
    _load_env_file()

    app = Flask(__name__, instance_relative_config=True)

    Path(app.instance_path).mkdir(
        parents=True,
        exist_ok=True
    )

    database_uri = _database_uri(app.instance_path)

    app.config.update(
        SECRET_KEY=os.getenv(
            "SECRET_KEY",
            "change-me"
        ),

        SQLALCHEMY_DATABASE_URI=database_uri,

        SQLALCHEMY_TRACK_MODIFICATIONS=False,

        ADMIN_USERNAME=os.getenv(
            "ADMIN_USERNAME",
            "admin"
        ),

        ADMIN_PASSWORD=os.getenv(
            "ADMIN_PASSWORD",
            "change-me"
        )
    )

    # Neon бос қосылымдарды бірнеше минуттан соң жабады.
    # pool_pre_ping — сұраныс алдында қосылымды тексереді,
    # сонда "server closed the connection" қатесі шықпайды.
    if database_uri.startswith("postgresql"):
        app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
            "pool_pre_ping": True,
            "pool_recycle": 280,
        }

    db.init_app(app)

    # ==============================
    # JINJA FILTER: nl2br
    # ==============================
    # Мәтін алдымен экрандалады — HTML енгізу мүмкін емес,
    # тек жол ауыстыру <br> болып шығады.

    @app.template_filter("nl2br")
    def nl2br(value):
        if value is None:
            return ""

        text = str(escape(value))

        for tag in ("&lt;br&gt;", "&lt;br/&gt;", "&lt;br /&gt;"):
            text = text.replace(tag, "<br>")

        return Markup(text.replace("\n", "<br>\n"))

    # ==============================
    # BLUEPRINTS
    # ==============================

    from .routes import site_bp, admin_bp

    app.register_blueprint(site_bp)

    app.register_blueprint(
        admin_bp,
        url_prefix="/admin"
    )

    # ==============================
    # DATABASE
    # ==============================

    with app.app_context():
        db.create_all()

        from .seed import seed_database

        seed_database()

    return app