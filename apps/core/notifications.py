"""Client générique pour remonter les erreurs serveur via webhook Discord."""

from __future__ import annotations

import json
import logging
import traceback
import urllib.error
import urllib.request

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

TRACEBACK_MAX_LENGTH = 2500
EMBED_DESCRIPTION_MAX = 4096
DISCORD_RED = 15548997  # #ED4245


def is_notification_configured() -> bool:
    if not getattr(settings, "ERROR_NOTIFY_ENABLED", True):
        return False
    webhook_url = getattr(settings, "DISCORD_WEBHOOK_URL", "") or ""
    return bool(str(webhook_url).strip())


def _app_name() -> str:
    return getattr(settings, "APP_NAME", None) or "Django App"


def _format_timestamp() -> str:
    now = timezone.localtime(timezone.now())
    tz_name = now.tzname() or settings.TIME_ZONE
    return now.strftime(f"%d/%m/%Y à %H:%M:%S {tz_name}")


def _user_email(request) -> str:
    user = getattr(request, "user", None)
    if user is None or not getattr(user, "is_authenticated", False):
        return "Anonyme"
    email = (getattr(user, "email", None) or "").strip()
    if email:
        return email
    username = getattr(user, "get_username", lambda: "")()
    return username or f"user#{getattr(user, 'pk', '?')}"


def _exception_summary(exception: BaseException | None) -> str:
    if exception is None:
        return "Réponse HTTP 500 (sans exception capturée)"
    return f"{exception.__class__.__name__}: {exception}"


def _format_traceback(exception: BaseException | None) -> str:
    if exception is None:
        return ""
    tb = "".join(
        traceback.format_exception(type(exception), exception, exception.__traceback__)
    )
    if len(tb) > TRACEBACK_MAX_LENGTH:
        tb = tb[: TRACEBACK_MAX_LENGTH - 20] + "\n… [tronqué]"
    return tb


def _truncate(text: str, max_length: int) -> str:
    if len(text) <= max_length:
        return text
    return text[: max_length - 20] + "\n… [tronqué]"


def build_error_payload(
    request,
    *,
    exception: BaseException | None = None,
    status_code: int = 500,
) -> dict:
    """Construit le payload d'alerte (embed Discord) pour une erreur serveur."""
    method = getattr(request, "method", "?")
    path = getattr(request, "get_full_path", lambda: getattr(request, "path", "?"))()
    description = "\n".join(
        [
            f"**Horodatage :** {_format_timestamp()}",
            f"**Utilisateur :** {_user_email(request)}",
            f"**Requête :** `{method} {path}`",
            f"**Erreur :** `{_exception_summary(exception)}`",
        ]
    )
    description = _truncate(description, EMBED_DESCRIPTION_MAX)

    embed: dict = {
        "title": f"Erreur {status_code} — {_app_name()}",
        "color": DISCORD_RED,
        "description": description,
    }
    tb = _format_traceback(exception)
    if tb:
        embed["fields"] = [
            {
                "name": "Traceback",
                "value": f"```{_truncate(tb, 1000)}```",
                "inline": False,
            }
        ]

    return {
        "username": _app_name()[:80],
        "allowed_mentions": {"parse": []},
        "embeds": [embed],
    }


def send_notification(payload: dict) -> bool:
    """Poste le payload JSON sur le webhook configuré. Ne lève jamais d'exception."""
    if not is_notification_configured():
        return False

    url = str(settings.DISCORD_WEBHOOK_URL).strip()
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return 200 <= response.status < 300
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
        logger.warning("Échec d'envoi de la notification d'erreur : %s", exc)
        return False
    except Exception:
        logger.exception("Erreur inattendue lors de l'envoi de la notification")
        return False


def notify_server_error(
    request,
    *,
    exception: BaseException | None = None,
    status_code: int = 500,
) -> bool:
    """Formate et envoie une alerte d'erreur serveur. Retourne True si envoyé."""
    if not is_notification_configured():
        return False
    payload = build_error_payload(
        request, exception=exception, status_code=status_code
    )
    return send_notification(payload)
