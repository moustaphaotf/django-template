from datetime import datetime, timezone as dt_timezone
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import AnonymousUser, User
from django.http import HttpResponse, HttpResponseServerError
from django.test import Client, RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import path

from apps.core.middleware import TelegramErrorNotificationMiddleware
from apps.core.telegram import (
    build_error_message,
    is_telegram_configured,
    notify_server_error,
    send_telegram_message,
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
    TELEGRAM_BOT_TOKEN="test-token",
    TELEGRAM_CHAT_ID="123456",
    TELEGRAM_NOTIFY_ENABLED=True,
    TIME_ZONE="UTC",
    USE_TZ=True,
)
class TelegramMessageBuilderTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_is_configured_when_token_and_chat_present(self):
        self.assertTrue(is_telegram_configured())

    @override_settings(TELEGRAM_BOT_TOKEN="", TELEGRAM_CHAT_ID="123")
    def test_not_configured_without_token(self):
        self.assertFalse(is_telegram_configured())

    @override_settings(TELEGRAM_NOTIFY_ENABLED=False)
    def test_disabled_via_flag(self):
        self.assertFalse(is_telegram_configured())

    def test_message_includes_app_name_timestamp_and_anonymous(self):
        request = self.factory.get("/admin/orders/?q=1")
        request.user = AnonymousUser()
        fixed = datetime(2026, 7, 27, 3, 22, 15, tzinfo=dt_timezone.utc)

        with patch("apps.core.telegram.timezone.now", return_value=fixed):
            message = build_error_message(
                request, exception=ValueError("échec critique"), status_code=500
            )

        self.assertIn("Erreur 500", message)
        self.assertIn("Cargo System", message)
        self.assertIn("27/07/2026 à 03:22:15 UTC", message)
        self.assertIn("Anonyme", message)
        self.assertIn("GET /admin/orders/?q=1", message)
        self.assertIn("ValueError: échec critique", message)

    def test_message_includes_authenticated_user_email(self):
        request = self.factory.post("/api/shipments/")
        request.user = MagicMock(
            is_authenticated=True,
            email="ops@cargo.example",
            get_username=MagicMock(return_value="ops"),
            pk=42,
        )
        message = build_error_message(
            request, exception=RuntimeError("boom"), status_code=500
        )
        self.assertIn("ops@cargo.example", message)
        self.assertNotIn("Anonyme", message)

    def test_message_falls_back_to_username_without_email(self):
        request = self.factory.get("/admin/")
        request.user = MagicMock(
            is_authenticated=True,
            email="",
            get_username=MagicMock(return_value="admin"),
            pk=1,
        )
        message = build_error_message(request, exception=None, status_code=500)
        self.assertIn("admin", message)

    @override_settings(APP_NAME="Autre App")
    def test_app_name_comes_from_settings(self):
        request = self.factory.get("/")
        request.user = AnonymousUser()
        message = build_error_message(request, exception=None)
        self.assertIn("Autre App", message)
        self.assertNotIn("Cargo System", message)


@override_settings(
    TELEGRAM_BOT_TOKEN="bot-token",
    TELEGRAM_CHAT_ID="-100999",
    TELEGRAM_NOTIFY_ENABLED=True,
)
class TelegramSendTests(SimpleTestCase):
    @patch("apps.core.telegram.urllib.request.urlopen")
    def test_send_posts_to_telegram_api(self, mock_urlopen):
        response = MagicMock()
        response.status = 200
        response.__enter__.return_value = response
        response.__exit__.return_value = False
        mock_urlopen.return_value = response

        self.assertTrue(send_telegram_message("hello"))
        self.assertTrue(mock_urlopen.called)
        request = mock_urlopen.call_args.args[0]
        self.assertIn("bot-token/sendMessage", request.full_url)
        self.assertEqual(request.get_method(), "POST")

    @patch("apps.core.telegram.urllib.request.urlopen", side_effect=TimeoutError)
    def test_send_swallows_network_errors(self, _mock_urlopen):
        self.assertFalse(send_telegram_message("hello"))

    @override_settings(TELEGRAM_NOTIFY_ENABLED=False)
    @patch("apps.core.telegram.send_telegram_message")
    def test_notify_noop_when_disabled(self, mock_send):
        request = RequestFactory().get("/")
        request.user = AnonymousUser()
        self.assertFalse(notify_server_error(request, exception=RuntimeError("x")))
        mock_send.assert_not_called()


@override_settings(
    ROOT_URLCONF="apps.core.tests.test_telegram_middleware",
    MIDDLEWARE=[
        "django.contrib.sessions.middleware.SessionMiddleware",
        "django.contrib.auth.middleware.AuthenticationMiddleware",
        "apps.core.middleware.TelegramErrorNotificationMiddleware",
    ],
    APP_NAME="Cargo System",
    TELEGRAM_BOT_TOKEN="test-token",
    TELEGRAM_CHAT_ID="42",
    TELEGRAM_NOTIFY_ENABLED=True,
    DEBUG=False,
)
class TelegramMiddlewareIntegrationTests(TestCase):
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
            side_effect=RuntimeError("telegram down"),
        ):
            response = self.client.get("/boom/")
        self.assertEqual(response.status_code, 500)


class TelegramMiddlewareUnitTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_process_exception_marks_request_to_avoid_duplicates(self):
        def get_response(request):
            return HttpResponseServerError("already handled")

        middleware = TelegramErrorNotificationMiddleware(get_response)
        request = self.factory.get("/x/")
        request.user = AnonymousUser()

        with patch(
            "apps.core.middleware.notify_server_error", return_value=True
        ) as mock_notify:
            middleware.process_exception(request, RuntimeError("x"))
            response = middleware(request)

        self.assertEqual(response.status_code, 500)
        self.assertEqual(mock_notify.call_count, 1)
