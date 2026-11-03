import pytest
from django.urls import reverse


pytestmark = pytest.mark.django_db


def test_login_hides_microsoft_button_in_mock_mode(client, settings):
    settings.MOCK_SSO = True
    response = client.get(reverse("account_login"))
    assert response.status_code == 200
    content = response.content.decode("utf-8")
    assert "Mode test actif" in content
    assert "Se connecter avec Microsoft" not in content


def test_login_shows_microsoft_button_when_mock_disabled(client, settings):
    settings.MOCK_SSO = False
    response = client.get(reverse("account_login"))
    assert response.status_code == 200
    content = response.content.decode("utf-8")
    assert "Se connecter avec Microsoft" in content
