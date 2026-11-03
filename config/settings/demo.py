"""Isolated, local-only demonstration. Never use these settings for deployment."""
from .local import *  # noqa: F403
from .base import BASE_DIR

HEPL_DEMO = True
DEBUG = True
ALLOWED_HOSTS = ["127.0.0.1", "localhost"]
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / ".local-demo" / "demo.sqlite3", "ATOMIC_REQUESTS": True}}
EMAIL_BACKEND = "django.core.mail.backends.dummy.EmailBackend"
INTERNAL_IPS = []
ACCOUNT_ALLOW_REGISTRATION = True
