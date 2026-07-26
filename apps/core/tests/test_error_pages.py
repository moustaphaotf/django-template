from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse

from apps.core.error_views import handler403, handler404, handler500


@override_settings(DEBUG=False, ROOT_URLCONF="config.urls")
class ErrorPagesTests(TestCase):
    def setUp(self):
        self.client = Client(raise_request_exception=False)
        self.factory = RequestFactory()

    def test_404_page_renders_unfold_layout(self):
        response = self.client.get("/this-page-does-not-exist/")
        self.assertEqual(response.status_code, 404)
        content = response.content.decode()
        self.assertIn("404", content)
        self.assertIn("Page introuvable", content)
        self.assertIn("unfold/css/styles.css", content)
        self.assertIn("Retour au tableau de bord", content)

    def test_403_handler_renders_unfold_layout(self):
        request = self.factory.get("/admin/")
        request.user = User.objects.create_user("denied", "d@x.c", "x")
        response = handler403(request, PermissionDenied("pas autorisé"))
        self.assertEqual(response.status_code, 403)
        content = response.content.decode()
        self.assertIn("403", content)
        self.assertIn("Accès refusé", content)
        self.assertIn("unfold/css/styles.css", content)
        self.assertIn("pas autorisé", content)

    def test_500_handler_renders_without_admin_each_context(self):
        request = self.factory.get("/admin/")
        request.user = User.objects.create_user("boom", "b@x.c", "x")
        response = handler500(request)
        self.assertEqual(response.status_code, 500)
        content = response.content.decode()
        self.assertIn("500", content)
        self.assertIn("Erreur serveur", content)
        self.assertIn("unfold/css/styles.css", content)
        self.assertIn(reverse("admin:index"), content)
