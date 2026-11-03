from __future__ import annotations

import typing

from allauth.account.adapter import DefaultAccountAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.urls import reverse

from .roles import assign_teacher_role
from .roles import ensure_default_membership
from .roles import is_teacher

if typing.TYPE_CHECKING:
    from allauth.socialaccount.models import SocialLogin
    from django.http import HttpRequest

    from french_test_app.users.models import User


class AccountAdapter(DefaultAccountAdapter):
    def get_login_redirect_url(self, request):
        user = request.user
        ensure_default_membership(user)
        if is_teacher(user):
            return reverse("quiz:teacher_dashboard")
        return reverse("quiz:dashboard")

    def is_open_for_signup(self, request: HttpRequest) -> bool:
        return getattr(settings, "ACCOUNT_ALLOW_REGISTRATION", True)

    def save_user(self, request, user, form, commit=True):
        user = super().save_user(request, user, form, commit=commit)
        assign_teacher_role(user)
        ensure_default_membership(user)
        return user


class SocialAccountAdapter(DefaultSocialAccountAdapter):
    def is_open_for_signup(
        self,
        request: HttpRequest,
        sociallogin: SocialLogin,
    ) -> bool:
        if getattr(settings, "MOCK_SSO", False):
            raise PermissionDenied("Connexion Microsoft desactivee en mode MOCK_SSO.")
        allowed_domains = {
            value.strip().lower()
            for value in getattr(settings, "SSO_ALLOWED_DOMAINS", [])
            if value.strip()
        }
        if allowed_domains:
            email = (sociallogin.user.email or "").strip().lower()
            if "@" not in email:
                raise PermissionDenied("Adresse e-mail manquante pour la connexion SSO.")
            domain = email.split("@", 1)[1]
            if domain not in allowed_domains:
                raise PermissionDenied("Ce domaine e-mail n'est pas autorisé.")
        return getattr(settings, "ACCOUNT_ALLOW_REGISTRATION", True)

    def populate_user(
        self,
        request: HttpRequest,
        sociallogin: SocialLogin,
        data: dict[str, typing.Any],
    ) -> User:
        """
        Populates user information from social provider info.

        See: https://docs.allauth.org/en/latest/socialaccount/advanced.html#creating-and-populating-user-instances
        """
        user = super().populate_user(request, sociallogin, data)
        if not user.name:
            if name := data.get("name"):
                user.name = name
            elif first_name := data.get("first_name"):
                user.name = first_name
                if last_name := data.get("last_name"):
                    user.name += f" {last_name}"
        return user

    def save_user(self, request: HttpRequest, sociallogin: SocialLogin, form=None):
        user = super().save_user(request, sociallogin, form)
        assign_teacher_role(user)
        ensure_default_membership(user)
        return user
