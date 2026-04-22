import json
from pathlib import Path

from django.core.management.base import BaseCommand

from french_test_app.quiz.models import Question


class Command(BaseCommand):
    help = "Load questions from the parsed JSON fixture into the database"

    def add_arguments(self, parser):
        parser.add_argument(
            "--fixture",
            default="french_test_app/fixtures/questions.json",
            help="Path to the questions JSON fixture",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Delete all existing questions before loading",
        )

    def handle(self, *args, **options):
        fixture_path = Path(options["fixture"])
        if not fixture_path.exists():
            self.stderr.write(self.style.ERROR(f"Fixture not found: {fixture_path}"))
            return

        if options["clear"]:
            deleted, _ = Question.objects.all().delete()
            self.stdout.write(f"Deleted {deleted} existing questions")

        with open(fixture_path, encoding="utf-8") as f:
            data = json.load(f)

        created = 0
        updated = 0
        for entry in data:
            fields = entry["fields"]
            _, was_created = Question.objects.update_or_create(
                exam_number=fields["exam_number"],
                question_number=fields["question_number"],
                defaults={
                    "category": fields["category"],
                    "question_text": fields["question_text"],
                    "option_1": fields["option_1"],
                    "option_2": fields["option_2"],
                    "option_3": fields["option_3"],
                    "option_4": fields["option_4"],
                    "option_a": fields.get("option_a", "Aucune"),
                    "option_t": fields.get("option_t", "Toutes"),
                    "correct_answer": fields["correct_answer"],
                    "explanation": fields.get("explanation", ""),
                    "reference_text": fields.get("reference_text", ""),
                },
            )
            if was_created:
                created += 1
            else:
                updated += 1

        self.stdout.write(
            self.style.SUCCESS(f"Loaded {created} new, {updated} updated questions ({created + updated} total)")
        )
