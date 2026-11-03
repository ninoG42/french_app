"""Authenticated PDF previews that also work without a browser PDF plug-in."""
from contextlib import contextmanager
from pathlib import PurePosixPath

import fitz
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.cache import never_cache

from .models import Resource


@contextmanager
def open_pdf(resource):
    try:
        with resource.pdf_file.open("rb") as source:
            document = fitz.open(stream=source.read(), filetype="pdf")
    except (OSError, ValueError, fitz.FileDataError) as error:
        raise Http404("Ce document n’est pas disponible.") from error
    try:
        if not document.is_pdf or document.is_encrypted or not document.page_count:
            raise Http404("Ce document ne peut pas être affiché.")
        yield document
    finally:
        document.close()


@login_required
@never_cache
def viewer(request, resource_id):
    resource = get_object_or_404(Resource, pk=resource_id)
    raw_page = request.GET.get("page", "1")
    if len(raw_page) > 6 or not raw_page.isascii() or not raw_page.isdigit():
        raise Http404("Page introuvable.")
    page = int(raw_page)
    with open_pdf(resource) as document:
        pages = document.page_count
    if not 1 <= page <= pages:
        raise Http404("Page introuvable.")
    return render(request, "quiz/document.html", {
        "resource": resource, "page": page, "pages": pages,
        "previous_page": page - 1 if page > 1 else None,
        "next_page": page + 1 if page < pages else None,
    })


@login_required
@never_cache
def page_image(request, resource_id, page):
    resource = get_object_or_404(Resource, pk=resource_id)
    with open_pdf(resource) as document:
        if not 1 <= page <= document.page_count:
            raise Http404("Page introuvable.")
        pdf_page = document[page - 1]
        scale = min(2, 1500 / max(1, pdf_page.rect.width), 2000 / max(1, pdf_page.rect.height))
        pixmap = pdf_page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False, colorspace=fitz.csRGB)
        png = pixmap.tobytes("png")
    return HttpResponse(png, content_type="image/png")


@login_required
@never_cache
def download(request, resource_id):
    resource = get_object_or_404(Resource, pk=resource_id)
    try:
        source = resource.pdf_file.open("rb")
    except OSError as error:
        raise Http404("Ce document n’est pas disponible.") from error
    return FileResponse(source, content_type="application/pdf", as_attachment=True,
                        filename=PurePosixPath(resource.pdf_file.name).name)
