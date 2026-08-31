from datetime import datetime, timezone as dt_timezone
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import AnonymousUser, User
from django.http import HttpResponse, HttpResponseServerError
from django.test import Client, RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import path

from apps.core.middleware import ErrorNotificationMiddleware
from apps.core.notifications import (
    build_error_payload,
    is_notification_configured,
    notify_server_error,
    send_notification,
)


def _boom_view(request):
    raise RuntimeError("explosion contrôlée")


def _manual_500_view(request):
    return HttpResponseServerError("ko")


def _ok_view(request):
    return HttpResponse("ok")


urlpatterns = [
    path("boom/", _boom_view),
    path("manual-500/", _manual_500_view),
    path("ok/", _ok_view),
]


@override_settings(
    APP_NAME="Cargo System",
    DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/123/abc",
    TIME_ZONE="UTC",
    USE_TZ=True,
)
class ErrorPayloadBuilderTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_is_configured_when_webhook_present(self):
        self.assertTrue(is_notification_configured())

    @override_settings(DISCORD_WEBHOOK_URL="")
    def test_not_configured_without_webhook(self):
        self.assertFalse(is_notification_configured())

    def test_payload_includes_app_name_timestamp_and_anonymous(self):
        request = self.factory.get("/admin/orders/?q=1")
        request.user = AnonymousUser()
        fixed = datetime(2026, 7, 27, 3, 22, 15, tzinfo=dt_timezone.utc)

        with patch("apps.core.notifications.timezone.now", return_value=fixed):
            payload = build_error_payload(
                request, exception=ValueError("échec critique"), status_code=500
            )

        embed = payload["embeds"][0]
        self.assertEqual(payload["username"], "Cargo System")
        self.assertIn("Erreur 500", embed["title"])
        self.assertIn("Cargo System", embed["title"])
        self.assertIn("27/07/2026 à 03:22:15 UTC", embed["description"])
        self.assertIn("Anonyme", embed["description"])
        self.assertIn("GET /admin/orders/?q=1", embed["description"])
        self.assertIn("ValueError: échec critique", embed["description"])

    def test_payload_includes_authenticated_user_email(self):
        request = self.factory.post("/api/shipments/")
        request.user = MagicMock(
            is_authenticated=True,
            email="ops@cargo.example",
            get_username=MagicMock(return_value="ops"),
            pk=42,
        )
        payload = build_error_payload(
            request, exception=RuntimeError("boom"), status_code=500
        )
        description = payload["embeds"][0]["description"]
        self.assertIn("ops@cargo.example", description)
        self.assertNotIn("Anonyme", description)

    def test_payload_falls_back_to_username_without_email(self):
        request = self.factory.get("/admin/")
        request.user = MagicMock(
            is_authenticated=True,
            email="",
            get_username=MagicMock(return_value="admin"),
            pk=1,
        )
        payload = build_error_payload(request, exception=None, status_code=500)
        self.assertIn("admin", payload["embeds"][0]["description"])

    @override_settings(APP_NAME="Autre App")
    def test_app_name_comes_from_settings(self):
        request = self.factory.get("/")
        request.user = AnonymousUser()
        payload = build_error_payload(request, exception=None)
        self.assertEqual(payload["username"], "Autre App")
        self.assertIn("Autre App", payload["embeds"][0]["title"])
        self.assertNotIn("Cargo System", payload["embeds"][0]["title"])


@override_settings(
    DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/999/token",
)
class NotificationSendTests(SimpleTestCase):
    @patch("apps.core.notifications.urllib.request.urlopen")
    def test_send_posts_to_configured_webhook(self, mock_urlopen):
        response = MagicMock()
        response.status = 204
        response.__enter__.return_value = response
        response.__exit__.return_value = False
        mock_urlopen.return_value = response

        self.assertTrue(send_notification({"content": "hello"}))
        self.assertTrue(mock_urlopen.called)
        request = mock_urlopen.call_args.args[0]
        self.assertEqual(
            request.full_url, "https://discord.com/api/webhooks/999/token"
        )
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.get_header("Content-type"), "application/json")

    @patch("apps.core.notifications.urllib.request.urlopen", side_effect=TimeoutError)
    def test_send_swallows_network_errors(self, _mock_urlopen):
        self.assertFalse(send_notification({"content": "hello"}))

    @override_settings(DISCORD_WEBHOOK_URL="")
    @patch("apps.core.notifications.send_notification")
    def test_notify_noop_without_webhook(self, mock_send):
        request = RequestFactory().get("/")
        request.user = AnonymousUser()
        self.assertFalse(notify_server_error(request, exception=RuntimeError("x")))
        mock_send.assert_not_called()


@override_settings(
    ROOT_URLCONF="apps.core.tests.test_error_notification_middleware",
    MIDDLEWARE=[
        "django.contrib.sessions.middleware.SessionMiddleware",
        "django.contrib.auth.middleware.AuthenticationMiddleware",
        "apps.core.middleware.ErrorNotificationMiddleware",
    ],
    APP_NAME="Cargo System",
    DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/1/test",
    DEBUG=False,
)
class ErrorNotificationMiddlewareIntegrationTests(TestCase):
    def setUp(self):
        self.client = Client(raise_request_exception=False)

    def test_exception_triggers_single_notification_with_email(self):
        user = User.objects.create_user(
            "alice", email="alice@example.com", password="secret"
        )
        self.client.force_login(user)

        with patch(
            "apps.core.middleware.notify_server_error", return_value=True
        ) as mock_notify:
            response = self.client.get("/boom/")

        self.assertEqual(response.status_code, 500)
        self.assertEqual(mock_notify.call_count, 1)
        args, kwargs = mock_notify.call_args
        self.assertEqual(kwargs["status_code"], 500)
        self.assertIsInstance(kwargs["exception"], RuntimeError)
        self.assertEqual(str(kwargs["exception"]), "explosion contrôlée")
        self.assertEqual(args[0].user.email, "alice@example.com")

    def test_manual_500_response_is_notified_once(self):
        with patch(
            "apps.core.middleware.notify_server_error", return_value=True
        ) as mock_notify:
            response = self.client.get("/manual-500/")

        self.assertEqual(response.status_code, 500)
        self.assertEqual(mock_notify.call_count, 1)
        _args, kwargs = mock_notify.call_args
        self.assertEqual(kwargs["status_code"], 500)
        self.assertIsNone(kwargs["exception"])

    def test_successful_response_is_not_notified(self):
        with patch(
            "apps.core.middleware.notify_server_error", return_value=True
        ) as mock_notify:
            response = self.client.get("/ok/")

        self.assertEqual(response.status_code, 200)
        mock_notify.assert_not_called()

    def test_notification_failure_does_not_break_error_handling(self):
        with patch(
            "apps.core.middleware.notify_server_error",
            side_effect=RuntimeError("webhook down"),
        ):
            response = self.client.get("/boom/")
        self.assertEqual(response.status_code, 500)


class ErrorNotificationMiddlewareUnitTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_process_exception_marks_request_to_avoid_duplicates(self):
        def get_response(request):
            return HttpResponseServerError("already handled")

        middleware = ErrorNotificationMiddleware(get_response)
        request = self.factory.get("/x/")
        request.user = AnonymousUser()

        with patch(
            "apps.core.middleware.notify_server_error", return_value=True
        ) as mock_notify:
            middleware.process_exception(request, RuntimeError("x"))
            response = middleware(request)

        self.assertEqual(response.status_code, 500)
        self.assertEqual(mock_notify.call_count, 1)
