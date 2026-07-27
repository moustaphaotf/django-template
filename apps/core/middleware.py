"""Middleware de notification Telegram pour les erreurs serveur (5xx)."""

from __future__ import annotations

import logging

from apps.core.telegram import notify_server_error

logger = logging.getLogger(__name__)

_NOTIFIED_ATTR = "_telegram_500_notified"


class TelegramErrorNotificationMiddleware:
    """Intercepte les erreurs 500 et les remonte sur Telegram.

    - ``process_exception`` : exceptions non gérées levées par une vue
    - ``process_response`` : réponses HTTP 5xx sans exception (évite les doublons)

    La configuration se fait uniquement via les variables d'environnement
    ``APP_NAME``, ``TELEGRAM_BOT_TOKEN``, ``TELEGRAM_CHAT_ID`` (et optionnellement
    ``TELEGRAM_NOTIFY_ENABLED``), pour réutiliser le même modèle sur d'autres apps.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if (
            getattr(response, "status_code", None) is not None
            and response.status_code >= 500
            and not getattr(request, _NOTIFIED_ATTR, False)
        ):
            self._safe_notify(request, exception=None, status_code=response.status_code)
        return response

    def process_exception(self, request, exception):
        setattr(request, _NOTIFIED_ATTR, True)
        self._safe_notify(request, exception=exception, status_code=500)
        return None

    @staticmethod
    def _safe_notify(request, *, exception, status_code: int) -> None:
        try:
            notify_server_error(
                request, exception=exception, status_code=status_code
            )
        except Exception:
            # Ne jamais faire échouer la requête à cause d'une alerte.
            logger.exception(
                "Impossible d'envoyer la notification Telegram pour une erreur %s",
                status_code,
            )
