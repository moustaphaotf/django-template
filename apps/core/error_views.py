"""Handlers HTTP 403 / 404 / 500 stylés Unfold."""

from __future__ import annotations

from django.contrib import admin
from django.http import (
    HttpResponseForbidden,
    HttpResponseNotFound,
    HttpResponseServerError,
)
from django.template import TemplateDoesNotExist, loader
from django.utils.translation import gettext as _
from django.views.decorators.csrf import requires_csrf_token

_ERROR_CONTEXT_KEYS = (
    "site_title",
    "site_header",
    "site_url",
    "site_symbol",
    "site_favicons",
    "login_image",
    "colors",
    "border_radius",
    "styles",
    "scripts",
    "theme",
    "environment",
    "environment_title_prefix",
)


def _fallback_context() -> dict:
    from django.conf import settings

    unfold = getattr(settings, "UNFOLD", {})
    return {
        "site_title": unfold.get("SITE_TITLE", "Cargo System"),
        "site_header": unfold.get("SITE_HEADER", "Cargo System"),
        "site_symbol": unfold.get("SITE_SYMBOL"),
        "colors": unfold.get("COLORS", {}),
        "border_radius": unfold.get("BORDER_RADIUS", "6px"),
        "styles": [],
        "scripts": [],
        "theme": unfold.get("THEME"),
        "site_favicons": [],
        "login_image": None,
        "site_url": "/",
    }


def _error_context(request, *, safe: bool = False, **extra) -> dict:
    """Contexte Unfold minimal pour les pages d'erreur.

    ``safe=True`` (500) évite ``each_context`` (sidebar / DB) pour limiter
    les erreurs en cascade.
    """
    if safe:
        context = _fallback_context()
    else:
        try:
            full = admin.site.each_context(request)
            context = {key: full[key] for key in _ERROR_CONTEXT_KEYS if key in full}
        except Exception:
            context = _fallback_context()
    context.update(extra)
    return context


def _render_error(request, template_name: str, status_class, context: dict, *, safe: bool = False):
    try:
        template = loader.get_template(template_name)
        body = template.render(context, request)
    except Exception:
        if not safe:
            raise
        title = context.get("title", "Error")
        body = f"<!doctype html><html><head><title>{title}</title></head>"
        body += f"<body><h1>{title}</h1></body></html>"
    return status_class(body)


@requires_csrf_token
def handler403(request, exception):
    context = _error_context(
        request,
        title=_("Accès refusé"),
        status_code=403,
        status_label="403",
        icon="lock",
        message=_(
            "Vous n'avez pas la permission d'accéder à cette page. "
            "Contactez un administrateur si vous pensez qu'il s'agit d'une erreur."
        ),
        exception=str(exception) if exception else "",
        primary_url="admin:index",
        primary_label=_("Retour au tableau de bord"),
    )
    try:
        return _render_error(request, "403.html", HttpResponseForbidden, context)
    except TemplateDoesNotExist:
        return HttpResponseForbidden("403 Forbidden")


@requires_csrf_token
def handler404(request, exception):
    from urllib.parse import quote

    exception_repr = exception.__class__.__name__
    try:
        message = exception.args[0]
    except (AttributeError, IndexError):
        pass
    else:
        if isinstance(message, str):
            exception_repr = message

    context = _error_context(
        request,
        title=_("Page introuvable"),
        status_code=404,
        status_label="404",
        icon="search_off",
        message=_(
            "La page demandée n'existe pas ou a été déplacée. "
            "Vérifiez l'adresse ou retournez au tableau de bord."
        ),
        request_path=quote(request.path),
        exception=exception_repr,
        primary_url="admin:index",
        primary_label=_("Retour au tableau de bord"),
    )
    try:
        return _render_error(request, "404.html", HttpResponseNotFound, context)
    except TemplateDoesNotExist:
        return HttpResponseNotFound("Not Found")


@requires_csrf_token
def handler500(request):
    context = _error_context(
        request,
        safe=True,
        title=_("Erreur serveur"),
        status_code=500,
        status_label="500",
        icon="error",
        message=_(
            "Une erreur inattendue s'est produite. "
            "Réessayez dans un instant ou contactez le support si le problème persiste."
        ),
        primary_url="admin:index",
        primary_label=_("Retour au tableau de bord"),
    )
    return _render_error(
        request, "500.html", HttpResponseServerError, context, safe=True
    )
