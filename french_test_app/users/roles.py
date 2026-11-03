from __future__ import annotations

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

from french_test_app.quiz.models import CourseGroup


TEACHER_GROUP_NAME = "Enseignants"


def is_teacher(user) -> bool:
    if not getattr(user, "is_authenticated", False):
        return False
    if not getattr(user, "is_active", False):
        return False
    if user.is_superuser:
        return True
    return user.groups.filter(name=TEACHER_GROUP_NAME).exists() or user.teaching_groups.exists()


def _teacher_emails() -> set[str]:
    values = getattr(settings, "TEACHER_EMAILS", [])
    return {value.strip().lower() for value in values if value.strip()}


def assign_teacher_role(user) -> bool:
    if not user.email:
        return False
    if user.email.lower() not in _teacher_emails():
        return False
    teacher_group, _ = Group.objects.get_or_create(name=TEACHER_GROUP_NAME)
    user.groups.add(teacher_group)
    return True


def ensure_default_membership(user) -> None:
    if not user.is_active:
        return
    default_name = getattr(settings, "DEFAULT_CLASS_NAME", "HEPL")
    group, _ = CourseGroup.objects.get_or_create(name=default_name)
    if is_teacher(user):
        group.teachers.add(user)
    else:
        group.students.add(user)


def ensure_initial_superuser_group() -> None:
    User = get_user_model()
    teacher_group, _ = Group.objects.get_or_create(name=TEACHER_GROUP_NAME)
    for user in User.objects.filter(is_superuser=True):
        user.groups.add(teacher_group)
