import json
import logging
import random
import re

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError
from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import AnswerLog, Question, Resource, UserQuestionProgress

logger = logging.getLogger(__name__)


def _get_filter_params(request):
    """Extract category, exam_number, strength, topic, and source filters from GET params."""
    category = request.GET.get("category", "")
    exam_number = request.GET.get("exam", "")
    strength = request.GET.get("strength", "")
    topic = request.GET.get("topic", "")
    source = request.GET.get("source", "")
    try:
        exam_number = int(exam_number)
    except (ValueError, TypeError):
        exam_number = None
    if strength not in ("weak", "medium", "strong"):
        strength = ""
    if source not in ("exam", "serie", "capsule"):
        source = ""
    return category, exam_number, strength, topic, source


def _build_filter_qs(category="", exam_number=None, strength="", topic="", source=""):
    """Build a query string from filter params."""
    parts = []
    if category:
        parts.append(f"category={category}")
    if exam_number:
        parts.append(f"exam={exam_number}")
    if strength:
        parts.append(f"strength={strength}")
    if topic:
        parts.append(f"topic={topic}")
    if source:
        parts.append(f"source={source}")
    return "?" + "&".join(parts) if parts else ""


def _filtered_questions(category, exam_number, topic="", source=""):
    """Return a base queryset filtered by category/exam/topic/source."""
    qs = Question.objects.all()
    if source and source in dict(Question.Source.choices):
        qs = qs.filter(source=source)
    if topic:
        qs = qs.filter(capsule_topic=topic)
    if category and category in dict(Question.Category.choices):
        qs = qs.filter(category=category)
    if exam_number:
        qs = qs.filter(exam_number=exam_number)
    return qs


def select_next_question(user, category=None, exam_number=None, strength_filter=None, topic=None, source=None):
    """
    Priority-based question selection algorithm.

    When strength_filter is set (e.g. "weak"), only questions with that
    exact strength are returned -- useful for the "repeat failed" mode.

    Default (no filter):
    1. Questions never seen (highest priority)
    2. Questions seen < 5 times, weighted by weakness
    3. Weak questions (correct_rate < 50%)
    4. Medium questions (50% <= correct_rate < 80%)
    5. Strong questions (occasional review)
    """
    base_qs = _filtered_questions(category, exam_number, topic or "", source or "")
    all_ids = set(base_qs.values_list("id", flat=True))

    if not all_ids:
        return None

    progress_map = {
        p.question_id: p
        for p in UserQuestionProgress.objects.filter(user=user, question_id__in=all_ids)
    }

    if strength_filter:
        filtered_ids = [
            qid for qid in all_ids
            if (prog := progress_map.get(qid)) and prog.strength == strength_filter
        ]
        if not filtered_ids:
            return None
        return Question.objects.get(pk=random.choice(filtered_ids))

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

    if unseen:
        chosen_id = random.choice(unseen)
    elif under_five:
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

    # Exam breakdown (source=exam only)
    exams = []
    exam_numbers = (
        Question.objects.filter(source=Question.Source.EXAM)
        .values_list("exam_number", flat=True)
        .distinct()
        .order_by("exam_number")
    )
    for exam_num in exam_numbers:
        exam_qs = Question.objects.filter(exam_number=exam_num, source=Question.Source.EXAM)
        exam_total = exam_qs.count()
        exam_progress = UserQuestionProgress.objects.filter(
            user=user, question__exam_number=exam_num, question__source=Question.Source.EXAM,
        )
        exam_seen = exam_progress.filter(times_shown__gt=0).count()
        exam_strong = exam_progress.filter(strength="strong").count()
        exam_weak = exam_progress.filter(strength="weak").count()
        exam_medium = exam_progress.filter(strength="medium").count()
        exams.append({
            "number": exam_num,
            "total": exam_total,
            "seen": exam_seen,
            "strong": exam_strong,
            "medium": exam_medium,
            "weak": exam_weak,
            "pct_complete": int(exam_seen / exam_total * 100) if exam_total else 0,
        })

    # Serie breakdown
    SERIE_LABELS = {7: "Série A", 8: "Série B"}
    series = []
    serie_numbers = (
        Question.objects.filter(source=Question.Source.SERIE)
        .values_list("exam_number", flat=True)
        .distinct()
        .order_by("exam_number")
    )
    for serie_num in serie_numbers:
        serie_qs = Question.objects.filter(exam_number=serie_num, source=Question.Source.SERIE)
        serie_total = serie_qs.count()
        serie_progress = UserQuestionProgress.objects.filter(
            user=user, question__exam_number=serie_num, question__source=Question.Source.SERIE,
        )
        serie_seen = serie_progress.filter(times_shown__gt=0).count()
        serie_strong = serie_progress.filter(strength="strong").count()
        serie_weak = serie_progress.filter(strength="weak").count()
        serie_medium = serie_progress.filter(strength="medium").count()
        series.append({
            "number": serie_num,
            "label": SERIE_LABELS.get(serie_num, f"Série {serie_num}"),
            "total": serie_total,
            "seen": serie_seen,
            "strong": serie_strong,
            "medium": serie_medium,
            "weak": serie_weak,
            "pct_complete": int(serie_seen / serie_total * 100) if serie_total else 0,
        })

    # Capsule topic breakdown
    capsule_topics = []
    topic_names = (
        Question.objects.filter(source=Question.Source.CAPSULE)
        .exclude(capsule_topic="")
        .values_list("capsule_topic", flat=True)
        .distinct()
    )
    for topic_name in sorted(topic_names):
        topic_qs = Question.objects.filter(capsule_topic=topic_name)
        topic_total = topic_qs.count()
        topic_progress = UserQuestionProgress.objects.filter(
            user=user, question__capsule_topic=topic_name
        )
        topic_seen = topic_progress.filter(times_shown__gt=0).count()
        topic_strong = topic_progress.filter(strength="strong").count()
        topic_weak = topic_progress.filter(strength="weak").count()
        topic_medium = topic_progress.filter(strength="medium").count()
        capsule_topics.append({
            "name": topic_name,
            "total": topic_total,
            "seen": topic_seen,
            "strong": topic_strong,
            "medium": topic_medium,
            "weak": topic_weak,
            "pct_complete": int(topic_seen / topic_total * 100) if topic_total else 0,
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
        "series": series,
        "capsule_topics": capsule_topics,
        "five_plus": five_plus,
        "seen_count": seen_count,
    }
    return render(request, "quiz/dashboard.html", context)


@login_required
def practice(request):
    category, exam_number, strength, topic, source = _get_filter_params(request)
    question = select_next_question(
        request.user, category, exam_number,
        strength_filter=strength or None,
        topic=topic or None,
        source=source or None,
    )

    if question is None:
        if strength:
            messages.success(request, "Bravo ! Plus aucune question à revoir dans cette sélection.")
        else:
            messages.warning(request, "Aucune question disponible avec ces filtres.")
        return redirect("quiz:dashboard")

    progress = UserQuestionProgress.objects.filter(user=request.user, question=question).first()
    filter_qs = _build_filter_qs(category, exam_number, strength, topic, source)

    context = {
        "question": question,
        "progress": progress,
        "filter_qs": filter_qs,
        "category": category,
        "exam_number": exam_number,
        "strength": strength,
        "topic": topic,
        "source": source,
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
    strength = request.POST.get("strength", "")
    topic = request.POST.get("topic", "")
    source = request.POST.get("source", "")
    filter_qs = _build_filter_qs(category, exam_number, strength, topic, source)

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

    category, exam_number, strength, topic, source = _get_filter_params(request)
    filter_qs = _build_filter_qs(category, exam_number, strength, topic, source)

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
    Splits on commas only so that empty slots (e.g. "3,A,,2") preserve
    position alignment rather than shifting subsequent answers.
    """
    tokens = [t.strip().upper() for t in raw.strip().split(",")]
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


@login_required
@require_POST
def ai_explain(request, question_id):
    """Call Google Gemini to generate a detailed explanation for a question."""
    api_key = settings.GEMINI_API_KEY
    if not api_key:
        return JsonResponse(
            {"error": "Clé API Gemini non configurée. Ajoutez GEMINI_API_KEY dans .env."},
            status=503,
        )

    question = get_object_or_404(Question, pk=question_id)

    options_text = "\n".join([
        f"1 - {question.option_1}",
        f"2 - {question.option_2}",
        f"3 - {question.option_3}",
        f"4 - {question.option_4}",
        f"A - {question.option_a}",
        f"T - {question.option_t}",
    ])

    prompt = f"""Tu es un professeur de français expert pour la préparation à l'examen OP001 (HEP Vaud).
Un étudiant te demande d'expliquer la question suivante de la section "{question.get_category_display()}".

**Question :**
{question.question_text}

**Options :**
{options_text}

**Réponse correcte : {question.correct_answer}**

Donne une explication complète et pédagogique en français. Structure ta réponse ainsi :
1. **Réponse** : Indique la bonne réponse et pourquoi elle est correcte.
2. **Raisonnement** : Explique la règle de grammaire, d'orthographe ou de vocabulaire en jeu.
3. **Pièges à éviter** : Signale les erreurs courantes et pourquoi les autres options sont fausses.
4. **Astuce** : Donne un moyen mnémotechnique ou un conseil pour retenir la règle.

Sois concis mais complet. Utilise un langage clair et accessible."""

    try:
        from google import genai

        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
        return JsonResponse({"explanation": response.text})
    except Exception:
        logger.exception("Gemini API call failed for question %d", question_id)
        return JsonResponse(
            {"error": "Erreur lors de l'appel à l'API Gemini. Réessayez plus tard."},
            status=502,
        )


@login_required
def resources(request):
    all_resources = Resource.objects.all()

    MATERIAL_ORDER = {
        "capsule": 0,
        "mise_en_situation": 1,
        "theorie": 2,
        "exercice": 3,
        "corrige": 4,
        "autre": 5,
    }

    topics_with_questions = set(
        Question.objects.filter(source=Question.Source.CAPSULE)
        .exclude(capsule_topic="")
        .values_list("capsule_topic", flat=True)
        .distinct()
    )

    category_sections = []
    for cat_value, cat_label in Question.Category.choices:
        topics_qs = (
            all_resources
            .filter(category=cat_value)
            .values_list("topic", flat=True)
            .distinct()
        )
        topics = []
        for topic_name in sorted(topics_qs):
            topic_resources = list(
                all_resources.filter(category=cat_value, topic=topic_name)
            )
            topic_resources.sort(
                key=lambda r: (MATERIAL_ORDER.get(r.material_type, 99), r.title)
            )
            caps_num = next(
                (r.capsule_number for r in topic_resources if r.capsule_number),
                None,
            )
            has_questions = topic_name in topics_with_questions
            question_count = (
                Question.objects.filter(capsule_topic=topic_name).count()
                if has_questions else 0
            )
            topics.append({
                "name": topic_name,
                "capsule_number": caps_num,
                "resources": topic_resources,
                "count": len(topic_resources),
                "has_questions": has_questions,
                "question_count": question_count,
            })
        topics.sort(key=lambda t: (t["capsule_number"] or 99, t["name"]))
        category_sections.append({
            "label": cat_label,
            "value": cat_value,
            "topics": topics,
            "total": sum(t["count"] for t in topics),
        })

    return render(request, "quiz/resources.html", {
        "sections": category_sections,
        "total_resources": all_resources.count(),
    })
