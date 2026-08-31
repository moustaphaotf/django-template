from .base import *  # noqa: F403

DEBUG = False
ERROR_NOTIFY_ENABLED = False

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}
