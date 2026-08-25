#!/bin/sh
set -e

echo "Waiting for database..."
python - <<'PY'
import os
import sys
import time

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")
django.setup()

from django.db import connection
from django.db.utils import OperationalError

deadline = time.time() + 60
while True:
    try:
        connection.ensure_connection()
        break
    except OperationalError as exc:
        if time.time() > deadline:
            print(f"Database unavailable after 60s: {exc}", file=sys.stderr)
            sys.exit(1)
        time.sleep(2)
print("Database is available.")
PY

echo "Applying migrations..."
python manage.py migrate --noinput

echo "Collecting static files..."
python manage.py collectstatic --noinput

exec "$@"
