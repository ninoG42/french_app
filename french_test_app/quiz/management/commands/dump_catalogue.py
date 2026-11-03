import json

from django.core.management.base import BaseCommand

from french_test_app.quiz.models import Module
from french_test_app.quiz.models import Question


class Command(BaseCommand):
    help = "Dump modules and questions to JSON."

    def add_arguments(self, parser):
        parser.add_argument(
            "output",
            nargs="?",
            default="-",
            help="Output file path or '-' for stdout",
        )

    def handle(self, *args, **options):
        payload = {"modules": [], "questions": []}

        for module in Module.objects.order_by("title", "pk"):
            payload["modules"].append(
                {
                    "title": module.title,
                    "description": module.description,
                    "category": module.category,
                    "is_published": module.is_published,
                }
            )

        for question in Question.objects.select_related("module").order_by(
            "source", "exam_number", "module__title", "question_number", "pk"
        ):
            payload["questions"].append(
                {
                    "source": question.source,
                    "exam_number": question.exam_number,
                    "question_number": question.question_number,
                    "module_title": question.module.title if question.module else None,
                    "capsule_topic": question.capsule_topic,
                    "category": question.category,
                    "question_text": question.question_text,
                    "option_1": question.option_1,
                    "option_2": question.option_2,
                    "option_3": question.option_3,
                    "option_4": question.option_4,
                    "option_a": question.option_a,
                    "option_t": question.option_t,
                    "correct_answer": question.correct_answer,
                    "explanation": question.explanation,
                    "reference_text": question.reference_text,
                    "teacher_checked": question.teacher_checked,
                }
            )

        output_data = json.dumps(payload, ensure_ascii=False, indent=2)
        output = options["output"]
        if output == "-":
            self.stdout.write(output_data)
            return
        with open(output, "w", encoding="utf-8") as handle:
            handle.write(output_data)
        self.stdout.write(self.style.SUCCESS(f"Catalogue dumped to {output}"))
