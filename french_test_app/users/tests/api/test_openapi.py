from http import HTTPStatus

import pytest
from django.urls import reverse


def test_api_docs_accessible_by_admin(admin_client):
    response = admin_client.get(url)
    assert response.status_code == HTTPStatus.OK


@pytest.mark.django_db
def test_api_docs_not_accessible_by_anonymous_users(client):


def test_api_schema_generated_successfully(admin_client):
    response = admin_client.get(url)
    assert response.status_code == HTTPStatus.OK
