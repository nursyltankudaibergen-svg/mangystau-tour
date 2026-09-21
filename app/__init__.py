import os
from pathlib import Path

from flask import Flask
from markupsafe import Markup
from flask_sqlalchemy import SQLAlchemy


db = SQLAlchemy()


def create_app():
    app = Flask(__name__, instance_relative_config=True)

    Path(app.instance_path).mkdir(
        parents=True,
        exist_ok=True
    )

    app.config.update(
        SECRET_KEY=os.getenv(
            "SECRET_KEY",
            "change-me"
        ),

        SQLALCHEMY_DATABASE_URI="sqlite:///"
        + str(
            Path(app.instance_path)
            / "mangystau.sqlite3"
        ),

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

    db.init_app(app)

    # ==============================
    # JINJA FILTER: nl2br
    # ==============================

    @app.template_filter("nl2br")
    def nl2br(value):
        if value is None:
            return ""

        return Markup(
            str(value).replace("\n", "<br>\n")
        )

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