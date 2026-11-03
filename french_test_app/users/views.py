from __future__ import annotations

from typing import TYPE_CHECKING

from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.mixins import UserPassesTestMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.generic import DetailView
from django.views.generic import RedirectView
from django.views.generic import UpdateView

from french_test_app.users.models import User
from french_test_app.users.roles import is_teacher

if TYPE_CHECKING:
    from django.db.models import QuerySet


class TeacherProfileRequiredMixin(UserPassesTestMixin):
    """Students must not open the personal profile pages."""

    def test_func(self) -> bool:
        return is_teacher(self.request.user)

    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            return HttpResponseRedirect(reverse("quiz:dashboard"))
        return super().handle_no_permission()


class UserDetailView(LoginRequiredMixin, TeacherProfileRequiredMixin, DetailView):
    model = User
    slug_field = "id"
    slug_url_kwarg = "id"

    def get_queryset(self):
        # Individual teaching records have their own group-scoped view.
        return super().get_queryset().filter(pk=self.request.user.pk)


user_detail_view = UserDetailView.as_view()


class UserUpdateView(LoginRequiredMixin, TeacherProfileRequiredMixin, SuccessMessageMixin, UpdateView):
    model = User
    fields = ["name"]
    success_message = _("Information successfully updated")

    def get_success_url(self) -> str:
        assert self.request.user.is_authenticated  # type guard
        return self.request.user.get_absolute_url()

    def get_object(self, queryset: QuerySet | None = None) -> User:
        assert self.request.user.is_authenticated  # type guard
        return self.request.user


user_update_view = UserUpdateView.as_view()


class UserRedirectView(LoginRequiredMixin, RedirectView):
    permanent = False

    def get_redirect_url(self) -> str:
        if is_teacher(self.request.user):
            return reverse("users:detail", kwargs={"pk": self.request.user.pk})
        return reverse("quiz:dashboard")


user_redirect_view = UserRedirectView.as_view()
