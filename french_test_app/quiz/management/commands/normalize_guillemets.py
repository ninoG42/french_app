from django.core.management.base import BaseCommand
from django.db import transaction

from french_test_app.quiz.models import Question
from french_test_app.quiz.rich_text import RICH_TEXT_FIELDS
from french_test_app.quiz.rich_text import convert_straight_quotes_to_guillemets


class Command(BaseCommand):
    help = (
        'Replace ASCII double quotes "..." with French guillemets « ... » '
        "in question text fields."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show changes without writing to the database.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        updated = 0
        quote_replacements = 0
        unpaired_fields = 0

        with transaction.atomic():
            for question in Question.objects.order_by("pk").iterator():
                changed = False
                for field in RICH_TEXT_FIELDS:
                    original = getattr(question, field) or ""
                    converted, count, unpaired = convert_straight_quotes_to_guillemets(original)
                    if count == 0:
                        continue
                    quote_replacements += count
                    if unpaired:
                        unpaired_fields += 1
                        self.stdout.write(
                            self.style.WARNING(
                                f"Q{question.pk}.{field}: unpaired quote left after conversion"
                            )
                        )
                    if converted != original:
                        setattr(question, field, converted)
                        changed = True
                        preview = converted if len(converted) < 160 else converted[:157] + "…"
                        self.stdout.write(f"Q{question.pk}.{field}: {preview}")
                if changed:
                    updated += 1
                    if not dry_run:
                        question.save(update_fields=list(RICH_TEXT_FIELDS))

            if dry_run:
                transaction.set_rollback(True)

        verb = "Would update" if dry_run else "Updated"
        self.stdout.write(
            self.style.SUCCESS(
                f"{verb} {updated} question(s), "
                f"{quote_replacements} quote mark(s) converted"
                + (f", {unpaired_fields} unpaired field(s)" if unpaired_fields else "")
                + (" (dry-run)" if dry_run else "")
            )
        )
