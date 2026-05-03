from __future__ import annotations

import pytest
from django.contrib.sessions.backends.db import SessionStore
from django.test import Client
from django.utils import timezone

from french_test_app.quiz.models import Question, UserQuestionProgress
from french_test_app.users.tests.factories import UserFactory


@pytest.fixture
def quiz_user(db):
    """A user for browser-based testing."""
    return UserFactory.create()


@pytest.fixture
def sample_questions(db):
    """Create 9 questions: 3 per category."""
    questions = []
    categories = ["syntaxe", "orthographe", "vocabulaire"]
    for i, cat in enumerate(categories):
        for j in range(1, 4):
            q_num = i * 20 + j
            questions.append(
                Question.objects.create(
                    exam_number=1,
                    question_number=q_num,
                    category=cat,
                    question_text=f"<b>Question {cat} {j}:</b> Choisissez la bonne réponse.",
                    option_1=f"Option 1 pour {cat} Q{j}",
                    option_2=f"Option 2 pour {cat} Q{j}",
                    option_3=f"Option 3 pour {cat} Q{j}",
                    option_4=f"Option 4 pour {cat} Q{j}",
                    option_a="Aucune",
                    option_t="Toutes",
                    correct_answer="2",
                    explanation=f"Explication pour {cat} Q{j}.",
                )
            )
    return questions


@pytest.fixture
def weak_progress(quiz_user, sample_questions):
    """
    Mark some questions as 'weak' so the revision mode has data.
    Makes the 3 orthographe questions weak (answered 5 times, 1 correct).
    """
    weak_questions = [q for q in sample_questions if q.category == "orthographe"]
    for q in weak_questions:
        UserQuestionProgress.objects.create(
            user=quiz_user,
            question=q,
            times_shown=5,
            times_correct=1,
            strength="weak",
            last_seen=timezone.now(),
        )
    return weak_questions


@pytest.fixture
def logged_in_page(page, live_server, quiz_user):
    """Force-login via Django test client and inject session cookie into Playwright."""
    client = Client()
    client.force_login(quiz_user)
    session_key = client.cookies["sessionid"].value

    page.goto(f"{live_server.url}/")
    page.context.add_cookies([{
        "name": "sessionid",
        "value": session_key,
        "url": live_server.url,
    }])
    return page
