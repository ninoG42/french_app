from django.conf import settings

from .roles import is_teacher


def allauth_settings(request):
    """Expose some settings from django-allauth in templates."""
    return {
        "ACCOUNT_ALLOW_REGISTRATION": settings.ACCOUNT_ALLOW_REGISTRATION,
        "is_teacher": is_teacher(request.user),
        "is_demo": getattr(settings, "HEPL_DEMO", False),
        "MOCK_SSO": getattr(settings, "MOCK_SSO", False),
    }
