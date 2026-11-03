import pytest
from django.urls import reverse

from french_test_app.quiz.forms import QuestionForm
from french_test_app.quiz.models import CourseGroup, Question
from french_test_app.quiz.rich_text import convert_straight_quotes_to_guillemets
from french_test_app.quiz.rich_text import sanitize_question_html

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    ("raw", "expected", "count", "unpaired"),
    [
        ('Dit "bonjour"', "Dit « bonjour »", 2, False),
        ('"A" et "B"', "« A » et « B »", 4, False),
        ("Déjà « ok »", "Déjà « ok »", 0, False),
        ('Texte "ouvert', "Texte « ouvert", 1, True),
        ("Sans guillemets", "Sans guillemets", 0, False),
    ],
)
def test_convert_straight_quotes_to_guillemets(raw, expected, count, unpaired):
    got, n, odd = convert_straight_quotes_to_guillemets(raw)
    assert got == expected
    assert n == count
    assert odd is unpaired



@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Mot <i>important</i>", "Mot <i>important</i>"),
        ("Mot <em>important</em>", "Mot <em>important</em>"),
        ("Mot <b>gras</b>", "Mot <b>gras</b>"),
        ("« citation »", "« citation »"),
        ("<script>alert(1)</script>ok", "alert(1)ok"),
        ('<b onclick="x">x</b>', "<b>x</b>"),
        ("a <br> b", "a <br> b"),
        ("a <BR/> b", "a <br> b"),
        ("<i>ouvert", "<i>ouvert</i>"),
        ("a <unknown>b</unknown> c", "a b c"),
        ("1 < 2 & 3 > 0", "1 &lt; 2 &amp; 3 &gt; 0"),
    ],
)
def test_sanitize_question_html(raw, expected):
    assert sanitize_question_html(raw) == expected


def test_question_form_sanitizes_question_text_and_options():
    form = QuestionForm(
        data={
            "source": Question.Source.EXAM,
            "exam_number": 1,
            "question_number": 1,
            "capsule_topic": "",
            "category": "syntaxe",
            "question_text": 'Texte <i>italique</i> et <script>bad</script> « ok »',
            "option_1": 'Réponse <b>A</b> <script>x</script>',
            "option_2": "B",
            "option_3": "C",
            "option_4": "D",
            "option_a": "Aucune",
            "option_t": "Toutes",
            "correct_answer": "1",
            "explanation": "",
            "reference_text": "",
            "teacher_checked": False,
        }
    )
    assert form.is_valid(), form.errors
    assert form.cleaned_data["question_text"] == "Texte <i>italique</i> et bad « ok »"
    assert form.cleaned_data["option_1"] == "Réponse <b>A</b> x"


def test_teacher_edit_form_exposes_visual_editor_and_help(client, django_user_model):
    teacher = django_user_model.objects.create_user(email="teacher-rich@example.test")
    group = CourseGroup.objects.create(name="Appui")
    group.teachers.add(teacher)
    question = Question.objects.create(
        exam_number=1,
        question_number=9,
        category="syntaxe",
        question_text="Mot <i>important</i> et <b>gras</b>",
        correct_answer="1",
        option_1="Oui",
        option_2="Non",
        option_3="Peut-être",
        option_4="Jamais",
    )
    client.force_login(teacher)
    response = client.get(reverse("quiz:teacher_question_edit", args=[question.pk]))
    assert response.status_code == 200
    body = response.content.decode()
    assert "question_rich_text.js" in body
    assert "affiche directement" in body
    assert "id_question_text" in body
    assert "important" in body and "gras" in body

