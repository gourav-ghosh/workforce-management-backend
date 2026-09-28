# Workforce Management Backend - production container
# Uses uv (https://docs.astral.sh/uv/) for fast Python dependency management.

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/usr/local

# Install uv (the fast Python package manager by Astral).
RUN pip install --no-cache-dir uv

WORKDIR /app

# Copy the entire project so uv can resolve the lock file and
# install dependencies declared in pyproject.toml.
COPY pyproject.toml uv.lock* ./
COPY manage.py entrypoint.sh ./
COPY config/ ./config/
COPY apps/ ./apps/

# Install runtime dependencies (no dev group) and the project itself.
RUN uv sync --frozen --no-dev --no-install-project || uv sync --no-dev --no-install-project

RUN groupadd --system django \
    && useradd --system --gid django --home /app django \
    && mkdir -p /app/media /app/staticfiles \
    && chown -R django:django /app \
    && chmod +x /app/entrypoint.sh

USER django

EXPOSE 8000

ENTRYPOINT ["/app/entrypoint.sh"]
# Bind to $PORT when the platform provides one (Railway/Render/Heroku-style
# PaaS) and fall back to 8000 for plain Docker Compose, where the bundled
# Nginx proxies to web:8000.
CMD ["sh", "-c", "exec gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers ${WEB_CONCURRENCY:-3} --timeout 60 --access-logfile -"]
