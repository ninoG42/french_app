from __future__ import annotations

import json
from dataclasses import dataclass

from django.db import transaction

from .models import Module
from .models import Question


VALID_ANSWERS = {"1", "2", "3", "4", "A", "T"}


@dataclass
class ImportErrorDetail:
    row: int
    message: str


def _normalize_record(item: dict) -> dict:
    if "fields" in item and isinstance(item["fields"], dict):
        return item["fields"]
    return item


def parse_question_payload(raw_payload: str) -> tuple[list[dict], list[ImportErrorDetail]]:
    try:
        payload = json.loads(raw_payload)
    except json.JSONDecodeError as exc:
        return [], [ImportErrorDetail(row=0, message=f"JSON invalide: {exc.msg}")]

    if not isinstance(payload, list):
        return [], [ImportErrorDetail(row=0, message="Le JSON doit etre une liste.")]

    rows: list[dict] = []
    errors: list[ImportErrorDetail] = []
    valid_categories = {choice[0] for choice in Question.Category.choices}

    for idx, item in enumerate(payload, start=1):
        if not isinstance(item, dict):
            errors.append(ImportErrorDetail(row=idx, message="Chaque element doit etre un objet JSON."))
            continue

        fields = _normalize_record(item)
        required = [
            "question_text",
            "option_1",
            "option_2",
            "option_3",
            "option_4",
            "correct_answer",
            "category",
        ]
        missing = [key for key in required if not fields.get(key)]
        if missing:
            errors.append(ImportErrorDetail(row=idx, message=f"Champs manquants: {', '.join(missing)}"))
            continue

        answer = str(fields["correct_answer"]).upper().strip()
        if answer not in VALID_ANSWERS:
            errors.append(ImportErrorDetail(row=idx, message="correct_answer doit etre dans 1,2,3,4,A,T"))
            continue

        category = str(fields["category"]).strip()
        if category not in valid_categories:
            errors.append(ImportErrorDetail(row=idx, message="categorie inconnue"))
            continue

        rows.append(
            {
                "source": Question.Source.MODULE,
                "category": category,
                "question_text": str(fields["question_text"]).strip(),
                "option_1": str(fields["option_1"]).strip(),
                "option_2": str(fields["option_2"]).strip(),
                "option_3": str(fields["option_3"]).strip(),
                "option_4": str(fields["option_4"]).strip(),
                "option_a": str(fields.get("option_a") or "Aucune").strip(),
                "option_t": str(fields.get("option_t") or "Toutes").strip(),
                "correct_answer": answer,
                "explanation": str(fields.get("explanation") or "").strip(),
                "reference_text": str(fields.get("reference_text") or "").strip(),
            }
        )

    return rows, errors


@transaction.atomic
def create_module_with_questions(
    *,
    module: Module,
    rows: list[dict],
    start_question_number: int = 1,
) -> int:
    question_number = start_question_number
    created = 0
    for row in rows:
        Question.objects.create(module=module, question_number=question_number, **row)
        question_number += 1
        created += 1
    return created
