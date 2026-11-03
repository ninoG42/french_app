from __future__ import annotations

from http import HTTPStatus
from typing import TYPE_CHECKING

import pytest
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.models import AnonymousUser
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import HttpRequest
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from django.contrib.auth.models import Group

from french_test_app.users.forms import UserAdminChangeForm
from french_test_app.users.roles import TEACHER_GROUP_NAME
from french_test_app.users.views import UserRedirectView
from french_test_app.users.views import UserUpdateView
from french_test_app.users.views import user_detail_view

if TYPE_CHECKING:
    from django.test import RequestFactory

    from french_test_app.users.models import User

pytestmark = pytest.mark.django_db


def _make_teacher(user: User) -> User:
    group, _ = Group.objects.get_or_create(name=TEACHER_GROUP_NAME)
    user.groups.add(group)
    return user


class TestUserUpdateView:
    """
    TODO:
        extracting view initialization code as class-scoped fixture
        would be great if only pytest-django supported non-function-scoped
        fixture db access -- this is a work-in-progress for now:
        https://github.com/pytest-dev/pytest-django/pull/258
    """

    def dummy_get_response(self, request: HttpRequest):
        return None

    def test_get_success_url(self, user: User, rf: RequestFactory):
        view = UserUpdateView()
        request = rf.get("/fake-url/")
        request.user = user

        view.request = request
        assert view.get_success_url() == f"/users/{user.pk}/"

    def test_get_object(self, user: User, rf: RequestFactory):
        view = UserUpdateView()
        request = rf.get("/fake-url/")
        request.user = user

        view.request = request

        assert view.get_object() == user

    def test_form_valid(self, user: User, rf: RequestFactory):
        view = UserUpdateView()
        request = rf.get("/fake-url/")

        # Add the session/message middleware to the request
        SessionMiddleware(self.dummy_get_response).process_request(request)
        MessageMiddleware(self.dummy_get_response).process_request(request)
        request.user = user

        view.request = request

        # Initialize the form
        form = UserAdminChangeForm()
        form.cleaned_data = {}
        form.instance = user
        view.form_valid(form)

        messages_sent = [m.message for m in messages.get_messages(request)]
        assert messages_sent == [_("Information successfully updated")]


class TestUserRedirectView:
    def test_teacher_goes_to_profile(self, user: User, rf: RequestFactory):
        teacher = _make_teacher(user)
        view = UserRedirectView()
        request = rf.get("/fake-url")
        request.user = teacher

        view.request = request
        assert view.get_redirect_url() == f"/users/{teacher.pk}/"

    def test_student_goes_to_dashboard(self, user: User, rf: RequestFactory):
        view = UserRedirectView()
        request = rf.get("/fake-url")
        request.user = user

        view.request = request
        assert view.get_redirect_url() == reverse("quiz:dashboard")


class TestUserDetailView:
    def test_teacher_authenticated(self, user: User, rf: RequestFactory):
        teacher = _make_teacher(user)
        request = rf.get("/fake-url/")
        request.user = teacher
        response = user_detail_view(request, pk=teacher.pk)

        assert response.status_code == HTTPStatus.OK

    def test_student_redirected_away(self, user: User, rf: RequestFactory):
        request = rf.get("/fake-url/")
        request.user = user
        response = user_detail_view(request, pk=user.pk)

        assert isinstance(response, HttpResponseRedirect)
        assert response.status_code == HTTPStatus.FOUND
        assert response.url == reverse("quiz:dashboard")

    def test_not_authenticated(self, user: User, rf: RequestFactory):
        request = rf.get("/fake-url/")
        request.user = AnonymousUser()
        response = user_detail_view(request, pk=user.pk)
        login_url = reverse(settings.LOGIN_URL)

        assert isinstance(response, HttpResponseRedirect)
        assert response.status_code == HTTPStatus.FOUND
        assert response.url == f"{login_url}?next=/fake-url/"
