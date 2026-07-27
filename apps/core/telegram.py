"""Client minimal pour remonter les erreurs 500 via Telegram Bot API."""

from __future__ import annotations

import json
import logging
import traceback
import urllib.error
import urllib.request
from html import escape
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

TELEGRAM_MAX_MESSAGE_LENGTH = 4096
TRACEBACK_MAX_LENGTH = 2500


def is_telegram_configured() -> bool:
    if not getattr(settings, "TELEGRAM_NOTIFY_ENABLED", True):
        return False
    token = getattr(settings, "TELEGRAM_BOT_TOKEN", "") or ""
    chat_id = getattr(settings, "TELEGRAM_CHAT_ID", "") or ""
    return bool(token.strip() and str(chat_id).strip())


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


def build_error_message(
    request,
    *,
    exception: BaseException | None = None,
    status_code: int = 500,
) -> str:
    """Construit le message Telegram HTML pour une erreur serveur."""
    method = getattr(request, "method", "?")
    path = getattr(request, "get_full_path", lambda: getattr(request, "path", "?"))()
    lines = [
        f"🚨 <b>Erreur {status_code}</b> — {_app_name()}",
        "",
        f"📅 <b>Horodatage :</b> {escape(_format_timestamp())}",
        f"👤 <b>Utilisateur :</b> {escape(_user_email(request))}",
        f"🔗 <b>Requête :</b> <code>{escape(f'{method} {path}')}</code>",
        f"💥 <b>Erreur :</b> <code>{escape(_exception_summary(exception))}</code>",
    ]
    tb = _format_traceback(exception)
    if tb:
        lines.extend(["", "<b>Traceback :</b>", f"<pre>{escape(tb)}</pre>"])

    message = "\n".join(lines)
    if len(message) > TELEGRAM_MAX_MESSAGE_LENGTH:
        message = message[: TELEGRAM_MAX_MESSAGE_LENGTH - 20] + "\n… [tronqué]"
    return message


def send_telegram_message(text: str) -> bool:
    """Envoie un message au chat configuré. Ne lève jamais d'exception."""
    if not is_telegram_configured():
        return False

    token = settings.TELEGRAM_BOT_TOKEN.strip()
    chat_id = str(settings.TELEGRAM_CHAT_ID).strip()
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps(
        {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return 200 <= response.status < 300
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
        logger.warning("Échec d'envoi de la notification Telegram : %s", exc)
        return False
    except Exception:
        logger.exception("Erreur inattendue lors de l'envoi Telegram")
        return False


def notify_server_error(
    request,
    *,
    exception: BaseException | None = None,
    status_code: int = 500,
) -> bool:
    """Formate et envoie une alerte d'erreur 500. Retourne True si envoyé."""
    if not is_telegram_configured():
        return False
    message = build_error_message(
        request, exception=exception, status_code=status_code
    )
    return send_telegram_message(message)
