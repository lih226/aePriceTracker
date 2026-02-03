web: python -c "from app import init_db; init_db()" && gunicorn --bind 0.0.0.0:$PORT --workers 2 app:app
