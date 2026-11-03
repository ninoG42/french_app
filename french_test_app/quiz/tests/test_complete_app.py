"""Regression checks for original features alongside the teaching space."""
import fitz
import pytest
from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from french_test_app.quiz.models import AnswerLog, Question, Resource, UserQuestionProgress
from french_test_app.users.models import User

pytestmark = pytest.mark.django_db


def test_original_catalog_filters(client, quiz_user, sample_questions):
    client.force_login(quiz_user)
    q = sample_questions[0]
    q.source = "capsule"
    q.capsule_topic = "Pronoms relatifs"
    q.save()
    for filters in ({"category": "vocabulaire"}, {"source": "capsule"}, {"topic": "Pronoms relatifs"}, {"exam": "1"}):
        response = client.get(reverse("quiz:practice"), filters)
        assert response.status_code == 200
        chosen = response.context["question"]
        if "category" in filters:
            assert chosen.category == filters["category"]
        if "source" in filters:
            assert chosen.source == filters["source"]
        if "topic" in filters:
            assert chosen.capsule_topic == filters["topic"]
        if "exam" in filters:
            assert chosen.exam_number == int(filters["exam"])
    assert client.get(reverse("quiz:practice"), {"exam": "999"}).status_code == 302


def test_revision_skip_and_correction(client, quiz_user, sample_questions, weak_progress):
    client.force_login(quiz_user)
    response = client.get(reverse("quiz:practice"), {"strength": "weak"})
    q = response.context["question"]
    assert q in weak_progress
    response = client.post(reverse("quiz:answer", args=[q.pk]), {"answer": "S", "strength": "weak"})
    feedback = client.get(response.url)
    assert feedback.context["last_log"].selected_answer == "S"
    assert feedback.context["last_log"].is_correct is False
    assert feedback.context["correct_text"] == q.option_2
    assert "strength=weak" in feedback.context["filter_qs"]
    assert "ai-explain" not in feedback.content.decode()


def test_resources_keep_documents_and_practice_links(client, quiz_user, sample_questions):
    q = sample_questions[0]
    q.capsule_topic = "Les pronoms"
    q.save()
    Resource.objects.create(title="Les pronoms — théorie", topic="Les pronoms", category=q.category, material_type="theorie", pdf_file="resources/pronoms.pdf")
    client.force_login(quiz_user)
    response = client.get(reverse("quiz:resources"))
    assert response.status_code == 200
    assert reverse("quiz:document", args=[Resource.objects.get().pk]) in response.content.decode()
    assert "Les pronoms" in response.content.decode()
    assert response.context["total_resources"] == 1


def test_real_pdf_import_without_ai(client, quiz_user):
    quiz_user.user_permissions.add(*Permission.objects.filter(content_type__app_label="quiz", codename__in=["add_question", "change_question"]))
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((60, 60), "Question 1\nChoisissez le verbe correct.\n1 - mange\n2 - mangent\n3 - manger\n4 - mangez\nA - Aucune\nT - Toutes\nLe sujet est au pluriel.")
    pdf = SimpleUploadedFile("corrige.pdf", doc.tobytes(), content_type="application/pdf")
    doc.close()
    client.force_login(quiz_user)
    response = client.post(reverse("quiz:upload"), {"corrige_pdf": pdf, "exam_number": "121", "answers": "2", "section1": "syntaxe", "section2": "orthographe", "section3": "vocabulaire"})
    assert response.status_code == 302
    question = Question.objects.get(exam_number=121, question_number=1)
    assert question.correct_answer == "2"
    assert question.option_2 == "mangent"
    assert "pluriel" in question.explanation


def test_students_cannot_reset_progress(client, quiz_user, sample_questions):
    other = User.objects.create_user(email="another@example.test")
    q = sample_questions[0]
    for user in (quiz_user, other):
        AnswerLog.objects.create(user=user, question=q, selected_answer="2", is_correct=True)
        UserQuestionProgress.objects.create(user=user, question=q, times_shown=1, times_correct=1)
    client.force_login(quiz_user)
    assert client.post(reverse("quiz:reset_progress")).status_code == 403
    assert AnswerLog.objects.filter(user=quiz_user).count() == 1
    assert UserQuestionProgress.objects.filter(user=quiz_user).count() == 1
    assert AnswerLog.objects.filter(user=other).count() == 1
    assert UserQuestionProgress.objects.filter(user=other).count() == 1


def test_teacher_can_reset_own_progress(client, sample_questions):
    from django.contrib.auth.models import Group

    from french_test_app.users.roles import TEACHER_GROUP_NAME

    teacher = User.objects.create_user(email="teacher-reset@example.test")
    teacher.groups.add(Group.objects.get_or_create(name=TEACHER_GROUP_NAME)[0])
    q = sample_questions[0]
    AnswerLog.objects.create(user=teacher, question=q, selected_answer="2", is_correct=True)
    UserQuestionProgress.objects.create(user=teacher, question=q, times_shown=1, times_correct=1)
    client.force_login(teacher)
    assert client.post(reverse("quiz:reset_progress")).status_code == 302
    assert not AnswerLog.objects.filter(user=teacher).exists()
    assert not UserQuestionProgress.objects.filter(user=teacher).exists()


def test_ai_endpoint_is_removed(client, quiz_user):
    client.force_login(quiz_user)
    assert client.post("/quiz/ai-explain/1/").status_code == 404


def test_catalogue_lists_examen_and_capsules(client, quiz_user, sample_questions):
    for number in (7, 8):
        Question.objects.create(exam_number=number, question_number=60, source="serie", category="syntaxe", correct_answer="1")
    Question.objects.create(exam_number=101, question_number=1, source="capsule", capsule_topic="Accord & syntaxe", category="syntaxe", correct_answer="1")
    client.force_login(quiz_user)
    response = client.get(reverse("quiz:catalogue"))
    assert response.status_code == 200
    content = response.content.decode()
    assert "Examen" in content
    assert "Série A" not in content
    assert "Série B" not in content
    assert "Accord%20%26%20syntaxe" in content
