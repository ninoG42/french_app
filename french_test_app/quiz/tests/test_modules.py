import pytest
from django.contrib.auth.models import Group
from django.urls import reverse

from french_test_app.quiz.importers import parse_question_payload
from french_test_app.quiz.models import Module
from french_test_app.quiz.models import Question
from french_test_app.users.tests.factories import UserFactory


pytestmark = pytest.mark.django_db


def _payload():
    return """
[
  {
    "question_text": "Question 1",
    "option_1": "A",
    "option_2": "B",
    "option_3": "C",
    "option_4": "D",
    "correct_answer": "1",
    "category": "syntaxe"
  }
]
"""


def test_parse_payload_supports_fixture_shape():
    payload = """
[
  {
    "model": "quiz.question",
    "pk": 1,
    "fields": {
      "question_text": "Texte",
      "option_1": "A",
      "option_2": "B",
      "option_3": "C",
      "option_4": "D",
      "correct_answer": "2",
      "category": "orthographe"
    }
  }
]
"""
    rows, errors = parse_question_payload(payload)
    assert not errors
    assert rows[0]["correct_answer"] == "2"


def test_student_cannot_access_teacher_modules(client):
    student = UserFactory()
    client.force_login(student)
    assert client.get(reverse("quiz:teacher_modules")).status_code == 403


def test_teacher_can_create_module_and_question(client):
    teacher = UserFactory(email="teacher@example.test")
    teacher_group, _ = Group.objects.get_or_create(name="Enseignants")
    teacher.groups.add(teacher_group)
    client.force_login(teacher)

    response = client.post(
        reverse("quiz:teacher_module_create"),
        data={
            "title": "Module test",
            "description": "Desc",
            "category": "syntaxe",
            "is_published": "on",
        },
    )
    assert response.status_code == 302
    module = Module.objects.get(title="Module test")
    create_question = client.post(
        reverse("quiz:teacher_module_detail", args=[module.pk]),
        data={
            "action": "create_question",
            "source": "module",
            "module": str(module.pk),
            "question_number": "1",
            "category": "syntaxe",
            "question_text": "Question manuelle",
            "option_1": "A",
            "option_2": "B",
            "option_3": "C",
            "option_4": "D",
            "option_a": "Aucune",
            "option_t": "Toutes",
            "correct_answer": "1",
            "explanation": "",
            "reference_text": "",
        },
    )
    assert create_question.status_code == 302
    question = Question.objects.get(module=module, question_number=1)
    assert question.source == Question.Source.MODULE


def test_module_filter_reaches_practice(client):
    student = UserFactory()
    module = Module.objects.create(title="M1", is_published=True)
    Question.objects.create(
        source=Question.Source.MODULE,
        module=module,
        exam_number=None,
        question_number=1,
        category=Question.Category.SYNTAXE,
        question_text="Q",
        option_1="A",
        option_2="B",
        option_3="C",
        option_4="D",
        correct_answer="1",
    )
    client.force_login(student)
    response = client.get(reverse("quiz:practice"), {"module": module.pk, "source": "module"})
    assert response.status_code == 200


def test_teacher_sees_existing_modules_not_owned(client):
    teacher = UserFactory(email="teacher@example.test")
    teacher_group, _ = Group.objects.get_or_create(name="Enseignants")
    teacher.groups.add(teacher_group)
    other = UserFactory(email="other@example.test")
    Module.objects.create(title="Existant", created_by=other, is_published=True)
    client.force_login(teacher)
    response = client.get(reverse("quiz:teacher_modules"))
    assert response.status_code == 200
    assert "Existant" in response.content.decode("utf-8")


def test_series_ui_create_edit_delete_question(client):
    teacher = UserFactory(email="teacher@example.test")
    teacher_group, _ = Group.objects.get_or_create(name="Enseignants")
    teacher.groups.add(teacher_group)
    question = Question.objects.create(
        source=Question.Source.SERIE,
        exam_number=77,
        question_number=1,
        category=Question.Category.SYNTAXE,
        question_text="Serie q1",
        option_1="A",
        option_2="B",
        option_3="C",
        option_4="D",
        correct_answer="1",
    )
    client.force_login(teacher)

    response = client.get(reverse("quiz:teacher_series_list"))
    assert response.status_code == 200

    add_response = client.post(
        reverse("quiz:teacher_series_detail", args=[77]),
        data={
            "action": "create_question",
            "source": "serie",
            "exam_number": "77",
            "question_number": "2",
            "category": "syntaxe",
            "question_text": "Serie q2",
            "option_1": "A",
            "option_2": "B",
            "option_3": "C",
            "option_4": "D",
            "option_a": "Aucune",
            "option_t": "Toutes",
            "correct_answer": "2",
            "explanation": "",
            "reference_text": "",
        },
    )
    assert add_response.status_code == 302
    created = Question.objects.get(source=Question.Source.SERIE, exam_number=77, question_number=2)

    edit_response = client.post(
        reverse("quiz:teacher_question_edit", args=[created.pk]),
        data={
            "source": "serie",
            "module": "",
            "exam_number": "77",
            "question_number": "2",
            "capsule_topic": "",
            "category": "syntaxe",
            "question_text": "Serie q2 edited",
            "option_1": "A",
            "option_2": "B",
            "option_3": "C",
            "option_4": "D",
            "option_a": "Aucune",
            "option_t": "Toutes",
            "correct_answer": "3",
            "explanation": "",
            "reference_text": "",
        },
    )
    assert edit_response.status_code == 302
    created.refresh_from_db()
    assert created.correct_answer == "3"

    delete_response = client.post(
        reverse("quiz:teacher_question_delete", args=[created.pk]),
        data={"confirm_delete": "1"},
    )
    assert delete_response.status_code == 302
    assert not Question.objects.filter(pk=created.pk).exists()
    assert Question.objects.filter(pk=question.pk).exists()
