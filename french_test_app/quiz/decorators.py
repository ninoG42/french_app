from functools import wraps

from django.core.exceptions import PermissionDenied

from french_test_app.users.roles import is_teacher


def teacher_required(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not is_teacher(request.user):
            raise PermissionDenied("Accès réservé aux enseignants.")
        return view_func(request, *args, **kwargs)

    return _wrapped
