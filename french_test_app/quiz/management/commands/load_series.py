"""Parse Série A/B PDFs as OP001-style QCM and load into Question model.

Uses the existing pdf_parser pipeline for question extraction, then
calls Gemini to identify correct answers since no corrigé PDFs exist
for these series.
"""

import json
import logging
import time
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from french_test_app.quiz.models import Question
from french_test_app.quiz.pdf_parser import parse_exam_pdfs

logger = logging.getLogger(__name__)

SERIES_CONFIG = [
    {
        "filename": "Série A.pdf",
        "exam_number": 7,
        "label": "Série A",
    },
    {
        "filename": "Série B.pdf",
        "exam_number": 8,
        "label": "Série B",
    },
]

SECTIONS = ("syntaxe", "orthographe", "vocabulaire")


def _get_gemini_answers(questions: list[dict], api_key: str, stdout=None) -> dict[int, str]:
    """Ask Gemini to identify correct answers for parsed questions."""
    import concurrent.futures

    from google import genai

    client = genai.Client(api_key=api_key)
    answers = {}

    batch_size = 10
    for i in range(0, len(questions), batch_size):
        batch = questions[i : i + batch_size]
        q_nums = [q["question_number"] for q in batch]
        prompt_parts = []
        for q in batch:
            prompt_parts.append(
                f"Question {q['question_number']}:\n"
                f"{q['question_text']}\n"
                f"1 - {q['option_1']}\n"
                f"2 - {q['option_2']}\n"
                f"3 - {q['option_3']}\n"
                f"4 - {q['option_4']}\n"
                f"A - {q['option_a']}\n"
                f"T - {q['option_t']}\n"
            )

        prompt = (
            "Tu es un expert en grammaire française pour l'examen OP001 (HEP Vaud).\n"
            "Pour chaque question ci-dessous, indique la bonne réponse.\n"
            "Réponds UNIQUEMENT en JSON: un objet avec les numéros de question comme clés "
            'et la réponse correcte comme valeur (un seul caractère: "1", "2", "3", "4", "A" ou "T").\n'
            "Exemple: {\"1\": \"3\", \"2\": \"A\", \"3\": \"2\"}\n\n"
            + "\n---\n".join(prompt_parts)
        )

        def _call():
            return client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
            )

        try:
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(_call)
                response = future.result(timeout=90)
            text = response.text.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1]
                text = text.rsplit("```", 1)[0]
            parsed = json.loads(text)
            batch_count = 0
            for k, v in parsed.items():
                q_num = int(k)
                if v in ("1", "2", "3", "4", "A", "T"):
                    answers[q_num] = v
                    batch_count += 1
            if stdout:
                stdout.write(f"    Batch Q{q_nums[0]}-Q{q_nums[-1]}: {batch_count} answers")
        except concurrent.futures.TimeoutError:
            if stdout:
                stdout.write(f"    Batch Q{q_nums[0]}-Q{q_nums[-1]}: TIMEOUT (skipped)")
        except Exception:
            logger.exception("Gemini batch %d-%d failed", i + 1, i + len(batch))
            if stdout:
                stdout.write(f"    Batch Q{q_nums[0]}-Q{q_nums[-1]}: ERROR (skipped)")

        if i + batch_size < len(questions):
            time.sleep(2)

    return answers


class Command(BaseCommand):
    help = "Parse Série A/B PDFs and load as QCM questions (uses Gemini for answer keys)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--source",
            default="aux_data",
            help="Path to folder containing Série PDFs",
        )
        parser.add_argument(
            "--no-gemini",
            action="store_true",
            help="Skip Gemini answer detection (load questions without correct answers)",
        )

    def handle(self, *args, **options):
        source_dir = Path(options["source"])
        api_key = settings.GEMINI_API_KEY

        if not api_key and not options["no_gemini"]:
            self.stderr.write(self.style.ERROR(
                "GEMINI_API_KEY not set. Use --no-gemini to skip answer detection."
            ))
            return

        for series in SERIES_CONFIG:
            pdf_path = source_dir / series["filename"]
            if not pdf_path.exists():
                self.stderr.write(self.style.WARNING(
                    f"Not found: {pdf_path}, skipping {series['label']}"
                ))
                continue

            self.stdout.write(f"Parsing {series['label']}...")

            parsed = parse_exam_pdfs(
                str(pdf_path),
                sections=SECTIONS,
                answers=None,
            )

            if not parsed:
                self.stderr.write(self.style.WARNING(f"No questions found in {series['label']}"))
                continue

            self.stdout.write(f"  Found {len(parsed)} questions")

            answers = {}
            if api_key and not options["no_gemini"]:
                self.stdout.write("  Asking Gemini for correct answers...")
                answers = _get_gemini_answers(parsed, api_key, stdout=self.stdout)
                self.stdout.write(f"  Got {len(answers)} answers from Gemini")

            created = 0
            updated = 0
            for q in parsed:
                correct = answers.get(q["question_number"], "")
                _, was_created = Question.objects.update_or_create(
                    exam_number=series["exam_number"],
                    question_number=q["question_number"],
                    defaults={
                        "source": Question.Source.SERIE,
                        "capsule_topic": "",
                        "category": q["category"],
                        "question_text": q["question_text"],
                        "option_1": q["option_1"],
                        "option_2": q["option_2"],
                        "option_3": q["option_3"],
                        "option_4": q["option_4"],
                        "option_a": q["option_a"],
                        "option_t": q["option_t"],
                        "correct_answer": correct,
                        "explanation": q.get("explanation", ""),
                        "reference_text": q.get("reference_text", ""),
                    },
                )
                if was_created:
                    created += 1
                else:
                    updated += 1

            self.stdout.write(self.style.SUCCESS(
                f"  {series['label']}: {created} created, {updated} updated"
            ))
