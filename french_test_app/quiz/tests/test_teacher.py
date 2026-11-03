import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.urls import reverse

from french_test_app.quiz.models import AnswerLog, CourseGroup, Question, UserQuestionProgress
from french_test_app.quiz.teacher import overview

pytestmark = pytest.mark.django_db


@pytest.fixture
def roster():
    User = get_user_model()
    teacher = User.objects.create_user(email="teacher@example.test")
    students = [User.objects.create_user(email=f"student{i}@example.test", name=f"Élève {i}") for i in range(4)]
    other = User.objects.create_user(email="outside@example.test", name="Confidentiel")
    group = CourseGroup.objects.create(name="Appui de français")
    group.teachers.add(teacher)
    group.students.add(*students)
    other_group = CourseGroup.objects.create(name="Autre cours")
    other_group.students.add(other)
    questions = [Question.objects.create(exam_number=1, question_number=i, category="syntaxe", question_text=f"Question {i}", correct_answer="1", option_1="Oui", option_2="Non", option_3="Peut-être", option_4="Jamais") for i in range(1, 4)]
    return teacher, students, other, group, other_group, questions


def test_access_requires_assigned_teacher(client, roster):
    teacher, students, other, group, other_group, questions = roster
    url = reverse("quiz:teacher_dashboard")
    assert client.get(url).status_code == 302
    client.force_login(students[0])
    assert client.get(url).status_code == 403
    client.force_login(teacher)
    assert client.get(url).status_code == 200
    assert client.get(url, {"group": other_group.pk}).status_code == 404
    assert client.get(url, {"group": "invalid"}).status_code == 404
    detail = reverse("quiz:teacher_student", args=[other.pk])
    assert client.get(detail, {"group": group.pk}).status_code == 404
    group.teachers.remove(teacher)
    assert client.get(url).status_code == 403


def test_first_attempts_and_group_isolation(client, roster):
    teacher, students, other, group, other_group, questions = roster
    for i, student in enumerate(students[:3]):
        AnswerLog.objects.create(user=student, question=questions[0], is_correct=i == 0, selected_answer="1" if i == 0 else "S")
        for _ in range(4):
            AnswerLog.objects.create(user=student, question=questions[0], is_correct=True, selected_answer="1")
        AnswerLog.objects.create(user=student, question=questions[1], is_correct=True, selected_answer="1")
    AnswerLog.objects.create(user=other, question=questions[0], is_correct=True, selected_answer="1")
    # Insufficient sample must not be ranked; a real zero is not "no data".
    AnswerLog.objects.create(user=students[0], question=questions[2], is_correct=False, selected_answer="2")
    ctx = overview(group.students.all())
    assert ctx["student_count"] == 4
    assert ctx["active_count"] == 3
    assert ctx["first_rate"] == 57  # 4/7, not inflated by successful repetitions.
    assert ctx["attempt_count"] == 19
    assert ctx["hardest"][0]["rate"] == 33
    assert ctx["easiest"][0]["rate"] == 100
    assert len(ctx["hardest"]) == 2
    assert ctx["students"][3]["rate"] is None
    client.force_login(teacher)
    response = client.get(reverse("quiz:teacher_dashboard"))
    assert response.status_code == 200
    assert b"Confidentiel" not in response.content
    assert b"Les acquis par domaine" in response.content
    assert b"Par capsule" not in response.content
    assert "no-store" in response.headers["Cache-Control"]


def test_empty_group(client, roster):
    teacher, students, other, group, other_group, questions = roster
    group.students.clear()
    client.force_login(teacher)
    response = client.get(reverse("quiz:teacher_dashboard"))
    assert response.status_code == 200
    assert response.context["first_rate"] is None
    assert response.context["student_count"] == 0


def test_student_detail_and_inactive_roster(client, roster):
    teacher, students, other, group, other_group, questions = roster
    UserQuestionProgress.objects.create(user=students[0], question=questions[0], times_shown=5, times_correct=4, strength="strong")
    client.force_login(teacher)
    response = client.get(reverse("quiz:teacher_student", args=[students[0].pk]), {"group": group.pk})
    assert response.status_code == 200
    assert response.context["row"]["strong"] == 1
    assert response.context["row"]["coverage"] == 33
    assert b"Par cat" in response.content
    assert b"Le parcours en d" not in response.content
    students[0].is_active = False
    students[0].save()
    assert client.get(reverse("quiz:teacher_student", args=[students[0].pk]), {"group": group.pk}).status_code == 404


def test_student_practice_is_recorded_and_visible(client, roster):
    teacher, students, other, group, other_group, questions = roster
    client.force_login(students[0])
    assert client.get(reverse("quiz:dashboard")).status_code == 200
    assert client.get(reverse("quiz:practice")).status_code == 200
    assert client.get(reverse("quiz:resources")).status_code == 200
    response = client.post(reverse("quiz:answer", args=[questions[0].pk]), {"answer": "1"})
    assert response.status_code == 302
    assert client.get(response.url).status_code == 200
    assert UserQuestionProgress.objects.get(user=students[0], question=questions[0]).times_correct == 1
    client.force_login(teacher)
    response = client.get(reverse("quiz:teacher_student", args=[students[0].pk]), {"group": group.pk})
    assert response.context["row"]["rate"] == 100
    assert response.context["row"]["attempts"] == 1


def test_import_requires_teacher_role(client, roster):
    teacher, students, *_ = roster
    client.force_login(students[0])
    assert client.get(reverse("quiz:upload")).status_code == 403
    assert client.post(reverse("quiz:upload")).status_code == 403
    client.force_login(teacher)
    assert client.get(reverse("quiz:upload")).status_code == 200


def test_question_bank_create_toggle_and_download_flag(client, roster):
    import json

    teacher, students, other, group, other_group, questions = roster
    q = questions[0]
    assert q.teacher_checked is False
    client.force_login(teacher)
    assert client.get(reverse("quiz:teacher_question_bank")).status_code == 200
    assert client.get(reverse("quiz:teacher_question_create")).status_code == 200
    assert client.post(
        reverse("quiz:teacher_question_toggle_checked", args=[q.pk]),
        {"next": reverse("quiz:teacher_question_bank")},
    ).status_code == 302
    q.refresh_from_db()
    assert q.teacher_checked is True
    response = client.get(reverse("quiz:catalogue_download"))
    assert response.status_code == 200
    payload = json.loads(response.content.decode())
    by_number = {item["question_number"]: item for item in payload["questions"] if item.get("exam_number") == 1}
    assert by_number[q.question_number]["teacher_checked"] is True


def test_demo_seed_refuses_normal_database():
    with pytest.raises(CommandError):
        call_command("seed_demo")


def test_profile_does_not_leak_other_students(client, roster):
    teacher, students, other, *_ = roster
    client.force_login(students[0])
    assert client.get(reverse("users:detail", args=[students[0].pk])).status_code == 200
    assert client.get(reverse("users:detail", args=[other.pk])).status_code == 404


def test_login_lands_in_the_right_space(rf, roster):
    from french_test_app.users.adapters import AccountAdapter
    teacher, students, *_ = roster
    request = rf.get("/")
    request.user = teacher
    assert AccountAdapter().get_login_redirect_url(request) == reverse("quiz:teacher_dashboard")
    request.user = students[0]
    assert AccountAdapter().get_login_redirect_url(request) == reverse("quiz:dashboard")
