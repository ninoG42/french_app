import types

import pytest
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory
from django.urls import reverse

from french_test_app.users.adapters import AccountAdapter
from french_test_app.users.adapters import SocialAccountAdapter
from french_test_app.users.roles import ensure_default_membership
from french_test_app.users.tests.factories import UserFactory


pytestmark = pytest.mark.django_db


def test_teacher_redirect_for_group_member():
    teacher_group, _ = Group.objects.get_or_create(name="Enseignants")
    teacher = UserFactory()
    teacher.groups.add(teacher_group)
    request = RequestFactory().get("/")
    request.user = teacher
    assert AccountAdapter().get_login_redirect_url(request) == reverse("quiz:teacher_dashboard")


def test_student_redirect_for_regular_user():
    student = UserFactory()
    request = RequestFactory().get("/")
    request.user = student
    assert AccountAdapter().get_login_redirect_url(request) == reverse("quiz:dashboard")


def test_social_signup_domain_allowlist(settings):
    settings.MOCK_SSO = False
    settings.SSO_ALLOWED_DOMAINS = ["hepl.ch"]
    adapter = SocialAccountAdapter()
    sociallogin = types.SimpleNamespace(user=types.SimpleNamespace(email="prof@hepl.ch"))
    assert adapter.is_open_for_signup(RequestFactory().get("/"), sociallogin) is True


def test_social_signup_domain_denied(settings):
    settings.MOCK_SSO = False
    settings.SSO_ALLOWED_DOMAINS = ["hepl.ch"]
    adapter = SocialAccountAdapter()
    sociallogin = types.SimpleNamespace(user=types.SimpleNamespace(email="x@example.com"))
    with pytest.raises(Exception):
        adapter.is_open_for_signup(RequestFactory().get("/"), sociallogin)


def test_social_signup_denied_when_mock_sso(settings):
    settings.MOCK_SSO = True
    adapter = SocialAccountAdapter()
    sociallogin = types.SimpleNamespace(user=types.SimpleNamespace(email="prof@hepl.ch"))
    with pytest.raises(PermissionDenied):
        adapter.is_open_for_signup(RequestFactory().get("/"), sociallogin)


def test_default_membership_created(settings):
    settings.DEFAULT_CLASS_NAME = "HEPL"
    user = UserFactory()
    ensure_default_membership(user)
    assert user.study_groups.filter(name="HEPL").exists()


def test_login_redirect_auto_assigns_default_group(settings):
    settings.DEFAULT_CLASS_NAME = "HEPL"
    student = UserFactory()
    request = RequestFactory().get("/")
    request.user = student
    AccountAdapter().get_login_redirect_url(request)
    assert student.study_groups.filter(name="HEPL").exists()
