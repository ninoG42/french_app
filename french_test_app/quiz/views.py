import logging
import random
import re

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import AnswerLog, Question, UserQuestionProgress

logger = logging.getLogger(__name__)


def _get_filter_params(request):
    """Extract category and exam_number filters from GET params."""
    category = request.GET.get("category", "")
    exam_number = request.GET.get("exam", "")
    try:
        exam_number = int(exam_number)
    except (ValueError, TypeError):
        exam_number = None
    return category, exam_number


def _filtered_questions(category, exam_number):
    """Return a base queryset filtered by category/exam."""
    qs = Question.objects.all()
    if category and category in dict(Question.Category.choices):
        qs = qs.filter(category=category)
    if exam_number and 1 <= exam_number <= 6:
        qs = qs.filter(exam_number=exam_number)
    return qs


def select_next_question(user, category=None, exam_number=None):
    """
    Priority-based question selection algorithm:
    1. Questions never seen (highest priority)
    2. Questions seen < 5 times, weighted by weakness
    3. Weak questions (correct_rate < 50%)
    4. Medium questions (50% <= correct_rate < 80%)
    5. Strong questions (occasional review)
    """
    base_qs = _filtered_questions(category, exam_number)
    all_ids = set(base_qs.values_list("id", flat=True))

    if not all_ids:
        return None

    progress_map = {
        p.question_id: p
        for p in UserQuestionProgress.objects.filter(user=user, question_id__in=all_ids)
    }

    unseen = []
    under_five = []
    weak = []
    medium = []
    strong = []

    for qid in all_ids:
        prog = progress_map.get(qid)
        if prog is None or prog.times_shown == 0:
            unseen.append(qid)
        elif prog.times_shown < 5:
            under_five.append((qid, prog))
        elif prog.strength == UserQuestionProgress.Strength.WEAK:
            weak.append(qid)
        elif prog.strength == UserQuestionProgress.Strength.MEDIUM:
            medium.append(qid)
        else:
            strong.append(qid)

    # Pick from highest priority non-empty bucket
    if unseen:
        chosen_id = random.choice(unseen)
    elif under_five:
        # Weight by weakness: lower correct_rate = higher weight
        weights = [max(0.1, 1.0 - p.correct_rate) for _, p in under_five]
        chosen_id = random.choices([qid for qid, _ in under_five], weights=weights, k=1)[0]
    elif weak:
        chosen_id = random.choice(weak)
    elif medium:
        chosen_id = random.choice(medium)
    elif strong:
        chosen_id = random.choice(strong)
    else:
        chosen_id = random.choice(list(all_ids))

    return Question.objects.get(pk=chosen_id)


@login_required
def dashboard(request):
    user = request.user
    total_questions = Question.objects.count()

    progress = UserQuestionProgress.objects.filter(user=user)
    strength_counts = dict(progress.values_list("strength").annotate(c=Count("id")).values_list("strength", "c"))

    strong_count = strength_counts.get("strong", 0)
    medium_count = strength_counts.get("medium", 0)
    weak_count = strength_counts.get("weak", 0)
    unseen_count = total_questions - progress.filter(times_shown__gt=0).count()

    total_answers = AnswerLog.objects.filter(user=user).count()
    correct_answers = AnswerLog.objects.filter(user=user, is_correct=True).count()
    overall_rate = correct_answers / total_answers if total_answers > 0 else 0

    # Anti-hasard score
    incorrect_answers = AnswerLog.objects.filter(user=user, is_correct=False).exclude(selected_answer="S").count()
    skip_count = AnswerLog.objects.filter(user=user, selected_answer="S").count()
    anti_hasard_score = correct_answers - (0.2 * incorrect_answers)

    # Category breakdown
    categories = []
    for cat_value, cat_label in Question.Category.choices:
        cat_qs = Question.objects.filter(category=cat_value)
        cat_total = cat_qs.count()
        cat_progress = UserQuestionProgress.objects.filter(user=user, question__category=cat_value)
        cat_seen = cat_progress.filter(times_shown__gt=0).count()
        cat_strong = cat_progress.filter(strength="strong").count()
        cat_weak = cat_progress.filter(strength="weak").count()
        cat_medium = cat_progress.filter(strength="medium").count()
        categories.append({
            "name": cat_label,
            "value": cat_value,
            "total": cat_total,
            "seen": cat_seen,
            "strong": cat_strong,
            "medium": cat_medium,
            "weak": cat_weak,
            "unseen": cat_total - cat_seen,
            "pct_complete": int(cat_seen / cat_total * 100) if cat_total else 0,
        })

    # Exam breakdown
    exams = []
    for exam_num in range(1, 7):
        exam_qs = Question.objects.filter(exam_number=exam_num)
        exam_total = exam_qs.count()
        exam_progress = UserQuestionProgress.objects.filter(user=user, question__exam_number=exam_num)
        exam_seen = exam_progress.filter(times_shown__gt=0).count()
        exam_strong = exam_progress.filter(strength="strong").count()
        exams.append({
            "number": exam_num,
            "total": exam_total,
            "seen": exam_seen,
            "strong": exam_strong,
            "pct_complete": int(exam_seen / exam_total * 100) if exam_total else 0,
        })

    # Questions meeting the 5x threshold
    five_plus = progress.filter(times_shown__gte=5).count()
    seen_count = strong_count + medium_count + weak_count

    context = {
        "total_questions": total_questions,
        "strong_count": strong_count,
        "medium_count": medium_count,
        "weak_count": weak_count,
        "unseen_count": unseen_count,
        "total_answers": total_answers,
        "correct_answers": correct_answers,
        "overall_rate": overall_rate,
        "anti_hasard_score": anti_hasard_score,
        "skip_count": skip_count,
        "categories": categories,
        "exams": exams,
        "five_plus": five_plus,
        "seen_count": seen_count,
    }
    return render(request, "quiz/dashboard.html", context)


@login_required
def practice(request):
    category, exam_number = _get_filter_params(request)
    question = select_next_question(request.user, category, exam_number)

    if question is None:
        messages.warning(request, "Aucune question disponible avec ces filtres.")
        return redirect("quiz:dashboard")

    progress = UserQuestionProgress.objects.filter(user=request.user, question=question).first()

    # Build filter query string to preserve across pages
    filter_qs = ""
    parts = []
    if category:
        parts.append(f"category={category}")
    if exam_number:
        parts.append(f"exam={exam_number}")
    if parts:
        filter_qs = "?" + "&".join(parts)

    context = {
        "question": question,
        "progress": progress,
        "filter_qs": filter_qs,
        "category": category,
        "exam_number": exam_number,
        "options": [
            ("1", question.option_1),
            ("2", question.option_2),
            ("3", question.option_3),
            ("4", question.option_4),
            ("A", question.option_a),
            ("T", question.option_t),
        ],
    }
    return render(request, "quiz/practice.html", context)


@login_required
@require_POST
def answer(request, question_id):
    question = get_object_or_404(Question, pk=question_id)
    selected = request.POST.get("answer", "S")  # S = skip

    if selected == "S":
        is_correct = False
    else:
        is_correct = selected == question.correct_answer

    AnswerLog.objects.create(
        user=request.user,
        question=question,
        selected_answer=selected,
        is_correct=is_correct,
    )

    progress, _ = UserQuestionProgress.objects.get_or_create(
        user=request.user,
        question=question,
    )
    progress.times_shown += 1
    if is_correct:
        progress.times_correct += 1
    progress.last_seen = timezone.now()
    progress.save(update_fields=["times_shown", "times_correct", "last_seen"])
    progress.update_strength()

    # Preserve filters
    category = request.POST.get("category", "")
    exam_number = request.POST.get("exam_number", "")
    filter_qs = ""
    parts = []
    if category:
        parts.append(f"category={category}")
    if exam_number:
        parts.append(f"exam={exam_number}")
    if parts:
        filter_qs = "?" + "&".join(parts)

    return redirect(f"/quiz/feedback/{question.pk}/{filter_qs}")


@login_required
def feedback(request, question_id):
    question = get_object_or_404(Question, pk=question_id)
    last_log = (
        AnswerLog.objects.filter(user=request.user, question=question)
        .order_by("-answered_at")
        .first()
    )
    progress = UserQuestionProgress.objects.filter(user=request.user, question=question).first()

    category, exam_number = _get_filter_params(request)
    filter_qs = ""
    parts = []
    if category:
        parts.append(f"category={category}")
    if exam_number:
        parts.append(f"exam={exam_number}")
    if parts:
        filter_qs = "?" + "&".join(parts)

    # Map answer codes to display text
    answer_map = {
        "1": question.option_1,
        "2": question.option_2,
        "3": question.option_3,
        "4": question.option_4,
        "A": question.option_a,
        "T": question.option_t,
        "S": "(Passée)",
    }

    context = {
        "question": question,
        "last_log": last_log,
        "progress": progress,
        "filter_qs": filter_qs,
        "correct_text": answer_map.get(question.correct_answer, ""),
        "selected_text": answer_map.get(last_log.selected_answer, "") if last_log else "",
        "options": [
            ("1", question.option_1),
            ("2", question.option_2),
            ("3", question.option_3),
            ("4", question.option_4),
            ("A", question.option_a),
            ("T", question.option_t),
        ],
    }
    return render(request, "quiz/feedback.html", context)


@login_required
@require_POST
def reset_progress(request):
    UserQuestionProgress.objects.filter(user=request.user).delete()
    AnswerLog.objects.filter(user=request.user).delete()
    messages.success(request, "Progression réinitialisée.")
    return redirect("quiz:dashboard")


VALID_ANSWERS = {"1", "2", "3", "4", "A", "T"}


def _parse_answers_string(raw: str) -> dict[int, str]:
    """
    Parse a comma-separated string of answers into {q_num: answer_code}.
    Accepts formats like "3,A,2,2,T,T,A,1,..." (60 values).
    """
    tokens = [t.strip().upper() for t in re.split(r"[,;\s]+", raw.strip()) if t.strip()]
    result = {}
    for i, tok in enumerate(tokens, start=1):
        if tok in VALID_ANSWERS:
            result[i] = tok
    return result


@login_required
def upload_exam(request):
    next_exam = (Question.objects.order_by("-exam_number").values_list("exam_number", flat=True).first() or 0) + 1

    if request.method != "POST":
        return render(request, "quiz/upload.html", {"next_exam": next_exam})

    corrige_file = request.FILES.get("corrige_pdf")
    questionnaire_file = request.FILES.get("questionnaire_pdf")
    exam_number = request.POST.get("exam_number", "")
    section1 = request.POST.get("section1", "syntaxe")
    section2 = request.POST.get("section2", "orthographe")
    section3 = request.POST.get("section3", "vocabulaire")
    answers_raw = request.POST.get("answers", "").strip()

    errors = []
    if not corrige_file:
        errors.append("Le PDF du corrigé est requis.")
    if not exam_number or not exam_number.isdigit():
        errors.append("Numéro d'exemple invalide.")
    if not answers_raw:
        errors.append("Les réponses correctes sont requises.")

    if errors:
        for e in errors:
            messages.error(request, e)
        return render(request, "quiz/upload.html", {"next_exam": next_exam})

    exam_number = int(exam_number)
    sections = (section1, section2, section3)
    answers = _parse_answers_string(answers_raw)

    if len(answers) < 1:
        messages.error(request, "Aucune réponse valide trouvée. Utilisez le format : 3,A,2,2,T,...")
        return render(request, "quiz/upload.html", {"next_exam": next_exam})

    try:
        from .pdf_parser import parse_exam_pdfs

        parsed = parse_exam_pdfs(
            corrige_file,
            questionnaire_file,
            sections=sections,
            answers=answers,
        )
    except Exception:
        logger.exception("PDF parsing failed")
        messages.error(request, "Erreur lors de l'analyse des PDF. Vérifiez le format.")
        return render(request, "quiz/upload.html", {"next_exam": next_exam})

    created = 0
    updated = 0
    for q in parsed:
        try:
            _, was_created = Question.objects.update_or_create(
                exam_number=exam_number,
                question_number=q["question_number"],
                defaults={
                    "category": q["category"],
                    "question_text": q["question_text"],
                    "option_1": q["option_1"],
                    "option_2": q["option_2"],
                    "option_3": q["option_3"],
                    "option_4": q["option_4"],
                    "option_a": q["option_a"],
                    "option_t": q["option_t"],
                    "correct_answer": q["correct_answer"],
                    "explanation": q["explanation"],
                    "reference_text": q["reference_text"],
                },
            )
            if was_created:
                created += 1
            else:
                updated += 1
        except IntegrityError:
            logger.exception("Failed to save question %d", q["question_number"])

    messages.success(
        request,
        f"Exemple {exam_number} importé : {created} nouvelles, {updated} mises à jour "
        f"({created + updated} questions au total).",
    )
    return redirect("quiz:dashboard")
