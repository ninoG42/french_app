import fitz
import pytest
from django.core.files.base import ContentFile
from django.urls import reverse
from french_test_app.quiz.models import Resource

pytestmark = pytest.mark.django_db


@pytest.fixture
def document(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    pdf = fitz.open()
    for label in ("Page une", "Page deux"):
        page = pdf.new_page()
        page.insert_text((60, 60), label)
    resource = Resource(title="Exercice PDF", topic="Accords")
    resource.pdf_file.save("exercice.pdf", ContentFile(pdf.tobytes()), save=True)
    pdf.close()
    return resource


def test_view_preview_download_and_pagination(client, quiz_user, document):
    client.force_login(quiz_user)
    url = reverse("quiz:document", args=[document.pk])
    response = client.get(url)
    assert response.status_code == 200
    assert response.context["pages"] == 2
    assert response.context["next_page"] == 2
    response = client.get(url, {"page": 2})
    assert response.context["previous_page"] == 1
    assert response.context["next_page"] is None
    image = client.get(reverse("quiz:document_page", args=[document.pk, 2]))
    assert image.status_code == 200
    assert image["Content-Type"] == "image/png"
    assert image.content.startswith(b"\x89PNG")
    download = client.get(reverse("quiz:document_download", args=[document.pk]))
    assert download["Content-Type"] == "application/pdf"
    assert "attachment" in download["Content-Disposition"]
    assert b"".join(download.streaming_content).startswith(b"%PDF")
    for page in (0, 3, "invalid", "9" * 100):
        assert client.get(url, {"page": page}).status_code == 404
    assert client.get(reverse("quiz:document_page", args=[document.pk, 3])).status_code == 404


def test_pdf_routes_require_login(client, document):
    for name, args in (("document", [document.pk]), ("document_page", [document.pk, 1]), ("document_download", [document.pk])):
        assert client.get(reverse(f"quiz:{name}", args=args)).status_code == 302


def test_missing_file_returns_404(client, quiz_user, document):
    document.pdf_file.storage.delete(document.pdf_file.name)
    client.force_login(quiz_user)
    for name, args in (("document", [document.pk]), ("document_page", [document.pk, 1]), ("document_download", [document.pk])):
        assert client.get(reverse(f"quiz:{name}", args=args)).status_code == 404


def test_resource_topics_and_counts_are_not_duplicated(client, quiz_user, document):
    Resource.objects.create(title="Corrigé", topic=document.topic, category=document.category, material_type="corrige", pdf_file=document.pdf_file.name)
    client.force_login(quiz_user)
    response = client.get(reverse("quiz:resources"))
    section = next(s for s in response.context["sections"] if s["value"] == document.category)
    assert len(section["topics"]) == 1
    assert section["total"] == 2
    assert response.context["total_resources"] == 2
