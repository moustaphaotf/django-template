FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=config.settings.production

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 1000 appuser \
    && useradd --uid 1000 --gid appuser --home-dir /app --shell /usr/sbin/nologin appuser

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=appuser:appuser . .

# collectstatic needs Django settings; DB is not contacted.
RUN DJANGO_SECRET_KEY=build-only \
    DJANGO_ALLOWED_HOSTS=localhost \
    DJANGO_DEBUG=false \
    python manage.py collectstatic --noinput \
    && chmod +x /app/entrypoint.sh

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import socket; s=socket.create_connection(('127.0.0.1',8000),2); s.close()"

ENTRYPOINT ["/app/entrypoint.sh"]
