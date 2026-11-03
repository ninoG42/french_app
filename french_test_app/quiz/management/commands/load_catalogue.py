import json

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from french_test_app.quiz.models import Module
from french_test_app.quiz.models import Question


class Command(BaseCommand):
    help = "Load and merge modules/questions from a catalogue dump."

    def add_arguments(self, parser):
        parser.add_argument("input", nargs="?", default="-", help="Input file path or '-' for stdin")
        parser.add_argument("--prune", action="store_true", help="Delete records not present in input")

    def _read_payload(self, source: str):
        if source == "-":
            raw = self.stdin.read()
        else:
            with open(source, encoding="utf-8") as handle:
                raw = handle.read()
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise CommandError(f"Invalid JSON: {exc.msg}") from exc
        if not isinstance(payload, dict):
            raise CommandError("Payload must be an object with 'modules' and 'questions'.")
        payload.setdefault("modules", [])
        payload.setdefault("questions", [])
        return payload

    @transaction.atomic
    def handle(self, *args, **options):
        payload = self._read_payload(options["input"])
        module_map = {}
        seen_module_titles = set()
        for item in payload["modules"]:
            title = (item.get("title") or "").strip()
            if not title:
                raise CommandError("Every module requires a title.")
            module, _ = Module.objects.update_or_create(
                title=title,
                defaults={
                    "description": item.get("description", ""),
                    "category": item.get("category", ""),
                    "is_published": item.get("is_published", True),
                },
            )
            module_map[title] = module
            seen_module_titles.add(title)

        seen_question_keys = set()
        for item in payload["questions"]:
            source = item.get("source", Question.Source.EXAM)
            question_number = item.get("question_number")
            if question_number is None:
                raise CommandError("Every question needs question_number.")
            module_title = item.get("module_title")
            module = module_map.get(module_title) if module_title else None

            if module is None and module_title:
                module = Module.objects.filter(title=module_title).first()
            if source == Question.Source.MODULE and module is None:
                raise CommandError(f"Module question refers to unknown module '{module_title}'.")

            if module:
                question, _ = Question.objects.update_or_create(
                    module=module,
                    question_number=question_number,
                    defaults={
                        "source": Question.Source.MODULE,
                        "exam_number": None,
                        "category": item["category"],
                        "question_text": item["question_text"],
                        "option_1": item["option_1"],
                        "option_2": item["option_2"],
                        "option_3": item["option_3"],
                        "option_4": item["option_4"],
                        "option_a": item.get("option_a", "Aucune"),
                        "option_t": item.get("option_t", "Toutes"),
                        "correct_answer": item["correct_answer"],
                        "explanation": item.get("explanation", ""),
                        "reference_text": item.get("reference_text", ""),
                        "capsule_topic": "",
                        "teacher_checked": bool(item.get("teacher_checked", False)),
                    },
                )
                seen_question_keys.add(("module", module.title, question.question_number))
            else:
                exam_number = item.get("exam_number")
                if exam_number is None:
                    raise CommandError("Non-module questions require exam_number.")
                question, _ = Question.objects.update_or_create(
                    module=None,
                    exam_number=exam_number,
                    question_number=question_number,
                    defaults={
                        "source": source,
                        "category": item["category"],
                        "question_text": item["question_text"],
                        "option_1": item["option_1"],
                        "option_2": item["option_2"],
                        "option_3": item["option_3"],
                        "option_4": item["option_4"],
                        "option_a": item.get("option_a", "Aucune"),
                        "option_t": item.get("option_t", "Toutes"),
                        "correct_answer": item["correct_answer"],
                        "explanation": item.get("explanation", ""),
                        "reference_text": item.get("reference_text", ""),
                        "capsule_topic": item.get("capsule_topic", ""),
                        "teacher_checked": bool(item.get("teacher_checked", False)),
                    },
                )
                seen_question_keys.add(("exam", exam_number, question.question_number))

        if options["prune"]:
            for module in Module.objects.exclude(title__in=seen_module_titles):
                module.delete()
            for question in Question.objects.select_related("module").all():
                key = (
                    ("module", question.module.title, question.question_number)
                    if question.module
                    else ("exam", question.exam_number, question.question_number)
                )
                if key not in seen_question_keys:
                    question.delete()

        self.stdout.write(self.style.SUCCESS("Catalogue loaded successfully"))
