"""Shared topic breakdown (catégorie / examen / capsule / module) for student and teacher views."""
from __future__ import annotations

from django.db.models import Count

from .models import Module, Question, UserQuestionProgress

SERIE_A_EXAM_NUMBER = 7
EXAMEN_SERIE_NUMBER = 8
SERIE_LABELS = {EXAMEN_SERIE_NUMBER: "Examen"}


def exclude_serie_a(qs):
    return qs.exclude(source=Question.Source.SERIE, exam_number=SERIE_A_EXAM_NUMBER)


def exclude_serie_b(qs):
    return qs.exclude(source=Question.Source.SERIE, exam_number=EXAMEN_SERIE_NUMBER)


def exclude_hidden_series(qs):
    return exclude_serie_a(exclude_serie_b(qs))


def _user_ids(users) -> list[int]:
    if hasattr(users, "values_list"):
        return list(users.values_list("pk", flat=True))
    return [u.pk if hasattr(u, "pk") else int(u) for u in users]


def _avg_counts(user_ids: list[int], question_ids: list[int]) -> dict:
    """Average progress counts across users (exact for a single student)."""
    total = len(question_ids)
    n = max(len(user_ids), 1)
    if not question_ids or not user_ids:
        return {
            "total": total,
            "seen": 0,
            "strong": 0,
            "medium": 0,
            "weak": 0,
            "unseen": total,
            "pct_complete": 0,
        }
    prog = UserQuestionProgress.objects.filter(user_id__in=user_ids, question_id__in=question_ids)
    def avg(qs):
        return int(round(qs.count() / n))

    seen = avg(prog.filter(times_shown__gt=0))
    strong = avg(prog.filter(strength="strong"))
    medium = avg(prog.filter(strength="medium"))
    weak = avg(prog.filter(strength="weak"))
    return {
        "total": total,
        "seen": seen,
        "strong": strong,
        "medium": medium,
        "weak": weak,
        "unseen": max(total - seen, 0),
        "pct_complete": int(seen / total * 100) if total else 0,
    }


def build_topic_breakdown(users) -> dict:
    """Return categories / series / capsule_topics / modules like the student dashboard."""
    user_ids = _user_ids(users)

    categories = []
    for cat_value, cat_label in Question.Category.choices:
        cat_ids = list(
            exclude_hidden_series(Question.objects.filter(category=cat_value)).values_list("id", flat=True)
        )
        row = _avg_counts(user_ids, cat_ids)
        row.update(name=cat_label, value=cat_value, label=cat_label)
        categories.append(row)

    series = []
    serie_numbers = (
        Question.objects.filter(source=Question.Source.SERIE, exam_number=EXAMEN_SERIE_NUMBER)
        .order_by("exam_number")
        .values_list("exam_number", flat=True)
        .distinct()
    )
    for serie_num in serie_numbers:
        serie_ids = list(
            Question.objects.filter(exam_number=serie_num, source=Question.Source.SERIE).values_list(
                "id", flat=True
            )
        )
        row = _avg_counts(user_ids, serie_ids)
        row.update(
            number=serie_num,
            label=SERIE_LABELS.get(serie_num, "Examen"),
        )
        series.append(row)

    capsule_topics = []
    topic_names = (
        exclude_hidden_series(Question.objects.all())
        .exclude(capsule_topic="")
        .order_by("capsule_topic")
        .values_list("capsule_topic", flat=True)
        .distinct()
    )
    for topic_name in sorted(topic_names):
        topic_ids = list(
            exclude_hidden_series(Question.objects.filter(capsule_topic=topic_name)).values_list(
                "id", flat=True
            )
        )
        row = _avg_counts(user_ids, topic_ids)
        row.update(name=topic_name)
        capsule_topics.append(row)

    modules = []
    for module in Module.objects.filter(is_published=True).order_by("title"):
        module_ids = list(module.questions.values_list("id", flat=True))
        row = _avg_counts(user_ids, module_ids)
        row.update(id=module.pk, title=module.title)
        modules.append(row)

    visible_ids = list(exclude_serie_a(Question.objects.all()).values_list("id", flat=True))
    overall = _avg_counts(user_ids, visible_ids)
    strength_progress = UserQuestionProgress.objects.filter(
        user_id__in=user_ids,
    ).exclude(
        question__source=Question.Source.SERIE,
        question__exam_number=SERIE_A_EXAM_NUMBER,
    )
    n = max(len(user_ids), 1)
    strength_counts = {
        row["strength"]: int(round(row["c"] / n))
        for row in strength_progress.values("strength").annotate(c=Count("id"))
    }

    return {
        "categories": categories,
        "series": series,
        "capsule_topics": capsule_topics,
        "modules": modules,
        "total_questions": overall["total"],
        "seen_count": overall["seen"],
        "unseen_count": overall["unseen"],
        "strong_count": strength_counts.get("strong", 0),
        "medium_count": strength_counts.get("medium", 0),
        "weak_count": strength_counts.get("weak", 0),
    }
