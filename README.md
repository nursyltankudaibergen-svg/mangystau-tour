# Mangystau Tour — Flask + Admin + SQLite

Python Flask версия сайта с админ-панелью и базой SQLite.

## Запуск Windows
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python run.py

Сайт: http://127.0.0.1:5000
Админ: http://127.0.0.1:5000/admin
Логин: admin
Пароль: change-me

Перед публикацией обязательно поменяйте ADMIN_PASSWORD и SECRET_KEY через переменные окружения.

В админке можно менять цены, туры, логотип URL, hero-фото, тексты и видеть заявки.

Для production Flask-приложение лучше размещать на Python-хостинге/VPS, а не через Netlify Drop.
