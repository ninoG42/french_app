"""
End-to-end browser tests for the quiz app using Playwright.

Run with:
    pytest french_test_app/quiz/tests/test_e2e.py -v
    pytest french_test_app/quiz/tests/test_e2e.py -v --headed        # visible browser
    pytest french_test_app/quiz/tests/test_e2e.py -v --headed --slowmo=500
"""

from __future__ import annotations

import pytest
from playwright.sync_api import expect


# ---------------------------------------------------------------------------
# Flow 1: Dashboard
# ---------------------------------------------------------------------------

@pytest.mark.django_db(transaction=True)
def test_dashboard_loads(logged_in_page, live_server, sample_questions):
    page = logged_in_page
    page.goto(f"{live_server.url}/quiz/")

    expect(page).to_have_title("Tableau de bord — OP001")

    stat_cards = page.locator(".card-body .fs-2")
    expect(stat_cards).to_have_count(4)

    expect(page.get_by_text("Commencer l'entraînement")).to_be_visible()


@pytest.mark.django_db(transaction=True)
def test_dashboard_has_category_buttons(logged_in_page, live_server, sample_questions):
    page = logged_in_page
    page.goto(f"{live_server.url}/quiz/")

    category_section = page.locator(".card-title", has_text="Par catégorie").locator("..")
    for cat_name in ["Orthographe", "Syntaxe", "Vocabulaire"]:
        expect(category_section.locator("strong", has_text=cat_name)).to_be_visible()

    train_buttons = category_section.get_by_role("link", name="S'entraîner")
    expect(train_buttons).to_have_count(3)


# ---------------------------------------------------------------------------
# Flow 2: Full practice cycle
# ---------------------------------------------------------------------------

@pytest.mark.django_db(transaction=True)
def test_practice_full_cycle(logged_in_page, live_server, sample_questions):
    page = logged_in_page
    page.goto(f"{live_server.url}/quiz/")

    page.get_by_role("button", name="Commencer").click()

    expect(page.locator(".card-body p")).to_be_visible()

    answer_buttons = page.locator('button[name="answer"]')
    expect(answer_buttons.first).to_be_visible()

    page.locator('button[value="2"]').click()

    expect(page.locator(".alert")).to_be_visible()

    correct_badge = page.get_by_text("Correct")
    expect(correct_badge.first).to_be_visible()

    page.get_by_role("link", name="Question suivante").click()

    expect(page.locator(".card-body p")).to_be_visible()


@pytest.mark.django_db(transaction=True)
def test_incorrect_answer_shows_red(logged_in_page, live_server, sample_questions):
    page = logged_in_page
    page.goto(f"{live_server.url}/quiz/practice/")

    page.locator('button[value="1"]').click()

    alert = page.locator(".alert-danger")
    expect(alert).to_be_visible()
    expect(page.get_by_text("Incorrect")).to_be_visible()

    expect(page.get_by_text("Votre choix")).to_be_visible()


# ---------------------------------------------------------------------------
# Flow 3: Single category training
# ---------------------------------------------------------------------------

@pytest.mark.django_db(transaction=True)
def test_train_single_category(logged_in_page, live_server, sample_questions):
    page = logged_in_page
    page.goto(f"{live_server.url}/quiz/practice/?category=orthographe")

    expect(page.locator(".card-body p")).to_be_visible()

    cat_badge = page.locator(".badge", has_text="Orthographe")
    expect(cat_badge).to_be_visible()

    page.locator('button[value="2"]').click()

    next_link = page.get_by_role("link", name="Question suivante")
    href = next_link.get_attribute("href")
    assert "category=" in href


# ---------------------------------------------------------------------------
# Flow 4: Skip a question
# ---------------------------------------------------------------------------

@pytest.mark.django_db(transaction=True)
def test_skip_question(logged_in_page, live_server, sample_questions):
    page = logged_in_page
    page.goto(f"{live_server.url}/quiz/practice/")

    page.locator('button[value="S"]').click()

    expect(page.get_by_text("Passée")).to_be_visible()

    alert = page.locator(".alert-secondary")
    expect(alert).to_be_visible()

    success_alert = page.locator(".alert-success")
    expect(success_alert).to_have_count(0)
    danger_alert = page.locator(".alert-danger")
    expect(danger_alert).to_have_count(0)


# ---------------------------------------------------------------------------
# Flow 5: Repeat only failed (red) questions
# ---------------------------------------------------------------------------

@pytest.mark.django_db(transaction=True)
def test_revise_weak_questions(logged_in_page, live_server, sample_questions, weak_progress):
    page = logged_in_page
    page.goto(f"{live_server.url}/quiz/")

    weak_card = page.locator(".card.text-bg-danger")
    expect(weak_card).to_be_visible()
    weak_count_text = weak_card.locator(".fs-2").inner_text()
    assert int(weak_count_text) > 0

    weak_card.get_by_role("link", name="Réviser").click()

    expect(page.get_by_text("Mode révision")).to_be_visible()

    expect(page.locator(".card-body p")).to_be_visible()


@pytest.mark.django_db(transaction=True)
def test_revise_completes_with_bravo(logged_in_page, live_server, sample_questions, weak_progress):
    """
    Answer weak questions correctly enough times to promote them out of 'weak'
    (need >=50% rate with times_shown>=5), then verify the revision pool empties.
    Each weak question starts at 5 shown / 1 correct (20%).
    After 3 correct answers: 8 shown / 4 correct (50%) → medium.
    With 3 weak questions × 3 correct answers = 9 iterations.
    """
    page = logged_in_page
    page.goto(f"{live_server.url}/quiz/practice/?strength=weak")

    for _ in range(9):
        if "/quiz/" == page.url.replace(live_server.url, "").rstrip("/").split("?")[0].rstrip("/"):
            break
        expect(page.locator(".card-body p")).to_be_visible()
        page.locator('button[value="2"]').click()
        page.get_by_role("link", name="Question suivante").click()

    expect(page).to_have_url(f"{live_server.url}/quiz/")


# ---------------------------------------------------------------------------
# Flow 6: Category + failed filter combined
# ---------------------------------------------------------------------------

@pytest.mark.django_db(transaction=True)
def test_category_plus_weak_filter(logged_in_page, live_server, sample_questions, weak_progress):
    page = logged_in_page
    page.goto(f"{live_server.url}/quiz/practice/?category=orthographe&strength=weak")

    expect(page.get_by_text("Mode révision")).to_be_visible()
    expect(page.locator(".card-body p")).to_be_visible()


# ---------------------------------------------------------------------------
# Flow 7: Upload page
# ---------------------------------------------------------------------------

@pytest.mark.django_db(transaction=True)
def test_upload_page_loads(logged_in_page, live_server):
    page = logged_in_page
    page.goto(f"{live_server.url}/quiz/upload/")

    expect(page.locator('input[type="file"]').first).to_be_visible()

    expect(page.locator("textarea, input[name='answers']").first).to_be_visible()


# ---------------------------------------------------------------------------
# Flow 8: Reset progress
# ---------------------------------------------------------------------------

@pytest.mark.django_db(transaction=True)
def test_reset_progress(logged_in_page, live_server, sample_questions):
    page = logged_in_page

    page.goto(f"{live_server.url}/quiz/practice/")
    page.locator('button[value="2"]').click()
    page.get_by_role("link", name="Question suivante").click()

    page.goto(f"{live_server.url}/quiz/")

    page.on("dialog", lambda dialog: dialog.accept())

    page.get_by_role("button", name="Réinitialiser la progression").click()

    page.wait_for_url(f"{live_server.url}/quiz/")

    seen_text = page.locator("text=0 / 9")
    expect(seen_text).to_be_visible()
