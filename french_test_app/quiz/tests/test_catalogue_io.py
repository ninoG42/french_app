import io
import json
import tempfile

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from french_test_app.quiz.models import Module
from french_test_app.quiz.models import Question


pytestmark = pytest.mark.django_db


def test_seed_catalogue_refuses_when_questions_exist():
    Question.objects.create(
        source=Question.Source.EXAM,
        exam_number=1,
        question_number=1,
        category=Question.Category.SYNTAXE,
        question_text="Q",
        option_1="A",
        option_2="B",
        option_3="C",
        option_4="D",
        correct_answer="1",
    )
    with pytest.raises(CommandError):
        call_command("seed_catalogue")


def test_dump_load_roundtrip_keeps_same_primary_key():
    module = Module.objects.create(title="Module 1")
    question = Question.objects.create(
        source=Question.Source.MODULE,
        module=module,
        exam_number=None,
        question_number=1,
        category=Question.Category.SYNTAXE,
        question_text="Original",
        option_1="A",
        option_2="B",
        option_3="C",
        option_4="D",
        correct_answer="1",
    )
    original_pk = question.pk

    output = io.StringIO()
    call_command("dump_catalogue", "-", stdout=output)
    payload = json.loads(output.getvalue())
    payload["questions"][0]["correct_answer"] = "2"
    payload["questions"][0]["question_text"] = "Updated"

    with tempfile.NamedTemporaryFile("w+", encoding="utf-8", delete=False) as handle:
        json.dump(payload, handle)
        handle.flush()
        call_command("load_catalogue", handle.name)

    question.refresh_from_db()
    assert question.pk == original_pk
    assert question.correct_answer == "2"
    assert question.question_text == "Updated"


def test_load_without_prune_keeps_extra_questions():
    Question.objects.create(
        source=Question.Source.EXAM,
        exam_number=10,
        question_number=1,
        category=Question.Category.SYNTAXE,
        question_text="Keep me",
        option_1="A",
        option_2="B",
        option_3="C",
        option_4="D",
        correct_answer="1",
    )
    payload = {"modules": [], "questions": []}
    with tempfile.NamedTemporaryFile("w+", encoding="utf-8", delete=False) as handle:
        json.dump(payload, handle)
        handle.flush()
        call_command("load_catalogue", handle.name)
    assert Question.objects.filter(exam_number=10, question_number=1).exists()
