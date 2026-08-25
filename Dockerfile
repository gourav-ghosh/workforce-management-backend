# Workforce Management Backend - production container
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements/ ./requirements/
RUN pip install --no-cache-dir -r requirements/production.txt

COPY manage.py entrypoint.sh ./
COPY config/ ./config/
COPY apps/ ./apps/

RUN groupadd --system django \
    && useradd --system --gid django --home /app django \
    && mkdir -p /app/media /app/staticfiles \
    && chown -R django:django /app \
    && chmod +x /app/entrypoint.sh

USER django

EXPOSE 8000

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "60", "--access-logfile", "-"]
