from .base import *  # noqa: F403

DEBUG = False
TELEGRAM_NOTIFY_ENABLED = False

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}
