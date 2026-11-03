import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from french_test_app.quiz.models import Question


class Command(BaseCommand):
    help = "Seed the initial catalogue once. Refuses to overwrite existing questions."

    def add_arguments(self, parser):
        parser.add_argument(
            "--fixture",
            default="french_test_app/fixtures/questions.json",
            help="Path to the questions fixture file",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Allow seeding even when questions already exist",
        )

    def handle(self, *args, **options):
        fixture_path = Path(options["fixture"])
        if not fixture_path.exists():
            raise CommandError(f"Fixture not found: {fixture_path}")

        if Question.objects.exists() and not options["force"]:
            raise CommandError("Questions already exist. Refusing to overwrite. Use --force if intended.")

        with open(fixture_path, encoding="utf-8") as handle:
            data = json.load(handle)

        created = 0
        updated = 0
        for item in data:
            fields = item.get("fields", item)
            defaults = {
                "source": fields.get("source", "exam"),
                "capsule_topic": fields.get("capsule_topic", ""),
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
                "module_id": None,
            }
            _, was_created = Question.objects.update_or_create(
                exam_number=fields["exam_number"],
                question_number=fields["question_number"],
                module__isnull=True,
                defaults=defaults,
            )
            if was_created:
                created += 1
            else:
                updated += 1

        self.stdout.write(self.style.SUCCESS(f"Seeded catalogue: {created} created, {updated} updated"))
