"""Teaching views: dashboard plus full UI authoring for QCM questions."""
from datetime import timedelta
import json

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError
from django.db.models import Count, Max, OuterRef, Q, Subquery
from django.db.models.functions import TruncDate
from django.http import Http404
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from french_test_app.users.roles import is_teacher

from .forms import ModuleForm, ModuleQuestionCreateForm
from .forms import QuestionCreateForm
from .forms import QuestionForm
from .models import AnswerLog, CourseGroup, Module, Question, UserQuestionProgress
from .progress_breakdown import SERIE_A_EXAM_NUMBER, build_topic_breakdown, exclude_serie_a


def assigned_groups(user):
    if not is_teacher(user):
        return CourseGroup.objects.none()
    if user.is_superuser:
        return CourseGroup.objects.all()
    return CourseGroup.objects.filter(teachers=user)


def selected_group(request):
    groups = assigned_groups(request.user)
    if not groups.exists():
        raise PermissionDenied("Aucun groupe de cours ne vous est attribué.")
    group_id = request.GET.get("group", "")
    if group_id:
        if not group_id.isdecimal():
            raise Http404
        group = get_object_or_404(groups, pk=group_id)
    else:
        group = groups.first()
    return groups, group


def first_attempts(students):
    # Select the first recorded attempt (including skips), before any aggregation.
    first = AnswerLog.objects.filter(
        user_id=OuterRef("user_id"), question_id=OuterRef("question_id"),
    ).order_by("answered_at", "pk").values("pk")[:1]
    return AnswerLog.objects.filter(user__in=students, pk=Subquery(first))


def rate(correct, total):
    return round(correct / total * 100) if total else None


def overview(students):
    total_questions = exclude_serie_a(Question.objects.all()).count()
    first = first_attempts(students)
    summary = first.aggregate(total=Count("pk"), correct=Count("pk", filter=Q(is_correct=True)))
    per_user = {row["user_id"]: row for row in first.order_by().values("user_id").annotate(
        total=Count("pk"), correct=Count("pk", filter=Q(is_correct=True)),
    )}
    progress = {row["user_id"]: row for row in UserQuestionProgress.objects.filter(
        user__in=students, times_shown__gt=0,
    ).exclude(
        question__source=Question.Source.SERIE,
        question__exam_number=SERIE_A_EXAM_NUMBER,
    ).order_by().values("user_id").annotate(
        seen=Count("pk"), strong=Count("pk", filter=Q(strength="strong")),
        weak=Count("pk", filter=Q(strength="weak")),
    )}
    activity = {row["user_id"]: row for row in AnswerLog.objects.filter(user__in=students).order_by().values(
        "user_id",
    ).annotate(last=Max("answered_at"), attempts=Count("pk"))}
    rows = []
    for student in students.order_by("name", "pk"):
        p = progress.get(student.pk, {})
        a = activity.get(student.pk, {})
        f = per_user.get(student.pk, {})
        rows.append({
            "student": student, "label": student.name or f"Étudiant {student.pk:03d}",
            "seen": p.get("seen", 0), "strong": p.get("strong", 0), "weak": p.get("weak", 0),
            "coverage": rate(p.get("seen", 0), total_questions) or 0,
            "rate": rate(f.get("correct", 0), f.get("total", 0)),
            "last": a.get("last"), "attempts": a.get("attempts", 0),
        })
    categories = []
    by_category = {r["question__category"]: r for r in first.order_by().values("question__category").annotate(
        total=Count("pk"), correct=Count("pk", filter=Q(is_correct=True)),
    )}
    for value, label in Question.Category.choices:
        c = by_category.get(value, {})
        categories.append({"label": label, "total": c.get("total", 0),
                           "rate": rate(c.get("correct", 0), c.get("total", 0))})
    ranking = list(first.order_by().values(
        "question_id", "question__question_text", "question__exam_number",
        "question__question_number", "question__capsule_topic", "question__category",
    ).annotate(total=Count("pk"), correct=Count("pk", filter=Q(is_correct=True))))
    for item in ranking:
        item["rate"] = rate(item["correct"], item["total"])
    eligible = [r for r in ranking if r["total"] >= 3]
    hardest = sorted(eligible, key=lambda r: (r["correct"] / r["total"], -r["total"], r["question_id"]))[:5]
    easiest = sorted(eligible, key=lambda r: (-r["correct"] / r["total"], -r["total"], r["question_id"]))[:5]
    start = timezone.localdate() - timedelta(days=13)
    daily = {r["day"]: r["total"] for r in AnswerLog.objects.filter(
        user__in=students, answered_at__date__gte=start,
    ).order_by().annotate(day=TruncDate("answered_at")).values("day").annotate(total=Count("pk"))}
    peak = max(daily.values(), default=1) or 1
    days = [{"date": start + timedelta(days=i), "total": daily.get(start + timedelta(days=i), 0)} for i in range(14)]
    for day in days:
        day["height"] = round(day["total"] / peak * 100)
    return {
        "students": rows, "student_count": len(rows), "active_count": sum(bool(r["last"]) for r in rows),
        "total_questions": total_questions, "first_rate": rate(summary["correct"], summary["total"]),
        "attempt_count": sum(r["attempts"] for r in rows), "categories": categories,
        "hardest": hardest, "easiest": easiest, "days": days,
    }


@login_required
@never_cache
def dashboard(request):
    groups, group = selected_group(request)
    context = overview(group.students.filter(is_active=True))
    context.update(groups=groups, group=group)
    return render(request, "quiz/teacher/dashboard.html", context)


@login_required
@never_cache
def student_detail(request, student_id):
    groups, group = selected_group(request)
    students = group.students.filter(is_active=True, pk=student_id)
    student = get_object_or_404(students)
    context = overview(students)
    # Per-student page: exact same topic bars as the student dashboard (not group averages).
    context.update(build_topic_breakdown([student]))
    context.update(
        groups=groups,
        group=group,
        student=student,
        row=context["students"][0],
        show_practice_actions=False,
    )
    return render(request, "quiz/teacher/student.html", context)


def _module_queryset(request):
    # Teacher UI must expose existing content, not only user-owned content.
    return Module.objects.select_related("created_by").prefetch_related("questions")


@login_required
@never_cache
def module_list(request):
    if not is_teacher(request.user):
        raise PermissionDenied("Acces reserve aux enseignants.")
    modules = _module_queryset(request).order_by("title")
    return render(request, "quiz/teacher/modules_list.html", {"modules": modules})


@login_required
@never_cache
def module_create(request):
    if not is_teacher(request.user):
        raise PermissionDenied("Acces reserve aux enseignants.")

    module_form = ModuleForm(request.POST or None)
    if request.method == "POST" and module_form.is_valid():
        module = module_form.save(commit=False)
        module.created_by = request.user
        module.save()
        return redirect("quiz:teacher_module_detail", module_id=module.pk)

    return render(
        request,
        "quiz/teacher/module_form.html",
        {"module_form": module_form},
    )


@login_required
@never_cache
def module_detail(request, module_id):
    if not is_teacher(request.user):
        raise PermissionDenied("Acces reserve aux enseignants.")
    module = get_object_or_404(_module_queryset(request), pk=module_id)
    next_question_number = (
        module.questions.order_by("-question_number").values_list("question_number", flat=True).first() or 0
    ) + 1
    create_form = ModuleQuestionCreateForm(
        request.POST or None,
        initial={
            "source": Question.Source.MODULE,
            "module": module,
            "question_number": next_question_number,
            "category": module.category or Question.Category.SYNTAXE,
        },
    )
    create_form.fields["source"].widget = create_form.fields["source"].hidden_widget()
    create_form.fields["module"].widget = create_form.fields["module"].hidden_widget()
    create_form.fields["exam_number"].widget = create_form.fields["exam_number"].hidden_widget()
    create_form.fields["capsule_topic"].widget = create_form.fields["capsule_topic"].hidden_widget()

    if request.method == "POST" and request.POST.get("action") == "create_question" and create_form.is_valid():
        question = create_form.save(commit=False)
        question.source = Question.Source.MODULE
        question.module = module
        question.exam_number = None
        if not question.question_number:
            question.question_number = next_question_number
        try:
            question.save()
        except IntegrityError:
            create_form.add_error("question_number", "Ce numero de question existe deja pour ce module.")
        else:
            return redirect("quiz:teacher_module_detail", module_id=module.pk)

    questions = module.questions.order_by("question_number")
    return render(
        request,
        "quiz/teacher/module_detail.html",
        {"module": module, "questions": questions, "create_form": create_form},
    )


@login_required
@require_POST
def module_delete(request, module_id):
    if not is_teacher(request.user):
        raise PermissionDenied("Acces reserve aux enseignants.")
    module = get_object_or_404(_module_queryset(request), pk=module_id)
    module.delete()
    return redirect("quiz:teacher_modules")


@login_required
@require_POST
def module_question_delete(request, module_id, question_id):
    if not is_teacher(request.user):
        raise PermissionDenied("Acces reserve aux enseignants.")
    module = get_object_or_404(_module_queryset(request), pk=module_id)
    question = get_object_or_404(module.questions, pk=question_id)
    question.delete()
    return redirect("quiz:teacher_module_detail", module_id=module_id)


@login_required
@never_cache
def series_list(request):
    if not is_teacher(request.user):
        raise PermissionDenied("Acces reserve aux enseignants.")
    series = (
        Question.objects.filter(source=Question.Source.SERIE)
        .values("exam_number")
        .annotate(total=Count("id"))
        .order_by("exam_number")
    )
    return render(request, "quiz/teacher/series_list.html", {"series": series})


@login_required
@never_cache
def series_detail(request, exam_number):
    if not is_teacher(request.user):
        raise PermissionDenied("Acces reserve aux enseignants.")
    questions = Question.objects.filter(source=Question.Source.SERIE, exam_number=exam_number).order_by("question_number")
    next_question_number = (questions.values_list("question_number", flat=True).last() or 0) + 1
    create_form = QuestionCreateForm(
        request.POST or None,
        initial={
            "source": Question.Source.SERIE,
            "exam_number": exam_number,
            "question_number": next_question_number,
            "category": Question.Category.SYNTAXE,
        },
    )
    create_form.fields["source"].widget = create_form.fields["source"].hidden_widget()
    create_form.fields["exam_number"].widget = create_form.fields["exam_number"].hidden_widget()
    create_form.fields["capsule_topic"].widget = create_form.fields["capsule_topic"].hidden_widget()

    if request.method == "POST" and request.POST.get("action") == "create_question" and create_form.is_valid():
        question = create_form.save(commit=False)
        question.source = Question.Source.SERIE
        question.module = None
        question.exam_number = exam_number
        if not question.question_number:
            question.question_number = next_question_number
        try:
            question.save()
        except IntegrityError:
            create_form.add_error("question_number", "Ce numero de question existe deja pour cette serie.")
        else:
            return redirect("quiz:teacher_series_detail", exam_number=exam_number)

    return render(
        request,
        "quiz/teacher/series_detail.html",
        {"exam_number": exam_number, "questions": questions, "create_form": create_form},
    )


@login_required
@never_cache
def question_bank(request):
    if not is_teacher(request.user):
        raise PermissionDenied("Acces reserve aux enseignants.")
    source = request.GET.get("source", "")
    exam_number = request.GET.get("exam", "")
    topic = request.GET.get("topic", "")
    checked = request.GET.get("checked", "")

    questions = Question.objects.select_related("module").exclude(source=Question.Source.MODULE)
    if source in {Question.Source.EXAM, Question.Source.SERIE, Question.Source.CAPSULE}:
        questions = questions.filter(source=source)
    if exam_number.isdecimal():
        questions = questions.filter(exam_number=int(exam_number))
    if topic:
        questions = questions.filter(capsule_topic=topic)
    if checked == "1":
        questions = questions.filter(teacher_checked=True)
    elif checked == "0":
        questions = questions.filter(teacher_checked=False)

    exams = Question.objects.filter(source=Question.Source.EXAM).order_by("exam_number").values_list("exam_number", flat=True).distinct()
    series = Question.objects.filter(source=Question.Source.SERIE).order_by("exam_number").values_list("exam_number", flat=True).distinct()
    topics = (
        Question.objects.filter(source=Question.Source.CAPSULE)
        .exclude(capsule_topic="")
        .order_by("capsule_topic")
        .values_list("capsule_topic", flat=True)
        .distinct()
    )
    questions = questions.order_by("teacher_checked", "source", "exam_number", "question_number", "id")

    return render(
        request,
        "quiz/teacher/question_bank.html",
        {
            "questions": questions,
            "exams": exams,
            "series": series,
            "topics": topics,
            "source": source,
            "exam_number": exam_number,
            "topic": topic,
            "checked": checked,
        },
    )


@login_required
@never_cache
def question_create(request):
    if not is_teacher(request.user):
        raise PermissionDenied("Acces reserve aux enseignants.")
    initial_source = request.GET.get("source") or Question.Source.CAPSULE
    if initial_source not in dict(Question.Source.choices):
        initial_source = Question.Source.CAPSULE
    initial = {
        "source": initial_source,
        "category": Question.Category.SYNTAXE,
        "option_a": "Aucune",
        "option_t": "Toutes",
        "teacher_checked": True,
    }
    exam_param = request.GET.get("exam", "")
    if exam_param.isdecimal():
        initial["exam_number"] = int(exam_param)
    topic_param = (request.GET.get("topic") or "").strip()
    if topic_param:
        initial["capsule_topic"] = topic_param
    form = QuestionCreateForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        try:
            form.save()
        except IntegrityError:
            form.add_error("question_number", "Ce numéro est déjà utilisé dans cet ensemble.")
        else:
            return redirect("quiz:teacher_question_bank")
    return render(
        request,
        "quiz/teacher/question_form.html",
        {"form": form, "question": None, "creating": True},
    )


@login_required
@require_POST
def question_toggle_checked(request, question_id):
    if not is_teacher(request.user):
        raise PermissionDenied("Acces reserve aux enseignants.")
    question = get_object_or_404(Question, pk=question_id)
    question.teacher_checked = not question.teacher_checked
    question.save(update_fields=["teacher_checked"])
    next_url = request.POST.get("next") or reverse("quiz:teacher_question_bank")
    return redirect(next_url)


def _redirect_after_question_edit(question):
    if question.source == Question.Source.MODULE and question.module_id:
        return reverse("quiz:teacher_module_detail", kwargs={"module_id": question.module_id})
    if question.source == Question.Source.SERIE and question.exam_number:
        return reverse("quiz:teacher_series_detail", kwargs={"exam_number": question.exam_number})
    return reverse("quiz:teacher_question_bank")


@login_required
@never_cache
def question_edit(request, question_id):
    if not is_teacher(request.user):
        raise PermissionDenied("Acces reserve aux enseignants.")
    question = get_object_or_404(Question.objects.select_related("module"), pk=question_id)
    if request.method != "POST":
        if request.GET.get("source") in dict(Question.Source.choices):
            question.source = request.GET["source"]
        exam_param = request.GET.get("exam", "")
        if exam_param.isdecimal():
            question.exam_number = int(exam_param)
        if "topic" in request.GET:
            question.capsule_topic = request.GET.get("topic") or ""
    form = QuestionForm(request.POST or None, instance=question)
    if request.method == "POST" and form.is_valid():
        try:
            updated = form.save()
        except IntegrityError:
            form.add_error("question_number", "Ce numero est deja utilise dans cet ensemble.")
        else:
            next_url = request.POST.get("next") or _redirect_after_question_edit(updated)
            return redirect(next_url)
    return render(request, "quiz/teacher/question_form.html", {"form": form, "question": question})


@login_required
@require_POST
def question_delete(request, question_id):
    if not is_teacher(request.user):
        raise PermissionDenied("Acces reserve aux enseignants.")
    question = get_object_or_404(Question.objects.select_related("module"), pk=question_id)
    next_url = request.POST.get("next") or _redirect_after_question_edit(question)
    # Require explicit second-step confirmation (browsers may skip stacked confirm()).
    if request.POST.get("confirm_delete") != "1":
        return redirect(request.POST.get("next") or reverse("quiz:teacher_question_edit", args=[question_id]))
    question.delete()
    return redirect(next_url)


@login_required
@never_cache
def catalogue_download(request):
    if not is_teacher(request.user):
        raise PermissionDenied("Acces reserve aux enseignants.")

    payload = {"modules": [], "questions": []}
    for module in Module.objects.prefetch_related("questions").order_by("title"):
        payload["modules"].append(
            {
                "title": module.title,
                "description": module.description,
                "category": module.category,
                "is_published": module.is_published,
            }
        )
    for question in Question.objects.select_related("module").order_by("source", "exam_number", "question_number", "pk"):
        payload["questions"].append(
            {
                "source": question.source,
                "exam_number": question.exam_number,
                "question_number": question.question_number,
                "module_title": question.module.title if question.module else None,
                "capsule_topic": question.capsule_topic,
                "category": question.category,
                "question_text": question.question_text,
                "option_1": question.option_1,
                "option_2": question.option_2,
                "option_3": question.option_3,
                "option_4": question.option_4,
                "option_a": question.option_a,
                "option_t": question.option_t,
                "correct_answer": question.correct_answer,
                "explanation": question.explanation,
                "reference_text": question.reference_text,
                "teacher_checked": question.teacher_checked,
            }
        )

    response = HttpResponse(
        json.dumps(payload, ensure_ascii=False, indent=2),
        content_type="application/json",
    )
    response["Content-Disposition"] = "attachment; filename=catalogue.json"
    return response
