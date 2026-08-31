from .base import *  # noqa: F403

DEBUG = False
DISCORD_WEBHOOK_URL = ""

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}
