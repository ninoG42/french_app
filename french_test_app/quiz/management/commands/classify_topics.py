"""Classify quiz questions into capsule topics via Amazon Bedrock (Claude Sonnet 4.6)."""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import as_completed
from pathlib import Path
from threading import Lock

import boto3
from botocore.config import Config
from django.core.management.base import BaseCommand
from django.core.management.base import CommandError
from django.db import transaction

from french_test_app.quiz.models import Question
from french_test_app.quiz.topic_taxonomy import SYSTEM_PROMPT
from french_test_app.quiz.topic_taxonomy import VALID_CODES
from french_test_app.quiz.topic_taxonomy import build_user_prompt
from french_test_app.quiz.topic_taxonomy import parse_model_json
from french_test_app.quiz.topic_taxonomy import question_payload
from french_test_app.quiz.topic_taxonomy import resolve_explanation
from french_test_app.quiz.topic_taxonomy import resolve_topic_label

DEFAULT_MODEL = "eu.anthropic.claude-sonnet-4-6"
DEFAULT_PROFILE = "accounting_test_admin"
DEFAULT_REGION = "eu-central-1"


class Command(BaseCommand):
    help = "Classify questions into capsule topics with Bedrock Claude Sonnet 4.6."

    def add_arguments(self, parser):
        parser.add_argument(
            "--model",
            default=DEFAULT_MODEL,
            help=f"Bedrock model id (default: {DEFAULT_MODEL})",
        )
        parser.add_argument("--profile", default=DEFAULT_PROFILE)
        parser.add_argument("--region", default=DEFAULT_REGION)
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Classify only the first N questions (0 = all).",
        )
        parser.add_argument(
            "--workers",
            type=int,
            default=4,
            help="Parallel Bedrock calls (default: 4).",
        )
        parser.add_argument(
            "--output",
            default="topic_classification.jsonl",
            help="JSONL path for raw model results.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Call Bedrock and write JSONL, but do not update the DB.",
        )
        parser.add_argument(
            "--apply-only",
            default="",
            help="Skip Bedrock; apply an existing JSONL file to the DB.",
        )
        parser.add_argument(
            "--resume",
            action="store_true",
            help="Skip question ids already present in the output JSONL.",
        )

    def handle(self, *args, **options):
        output_path = Path(options["output"])
        if options["apply_only"]:
            self._apply_jsonl(Path(options["apply_only"]), dry_run=False)
            return

        client = self._client(options["profile"], options["region"])
        qs = Question.objects.order_by("exam_number", "question_number", "pk")
        if options["limit"]:
            qs = qs[: options["limit"]]
        questions = list(qs)
        if not questions:
            raise CommandError("No questions found.")

        done_ids: set[int] = set()
        if options["resume"] and output_path.exists():
            done_ids = self._load_done_ids(output_path)
            questions = [q for q in questions if q.pk not in done_ids]
            self.stdout.write(f"Resuming: {len(done_ids)} already done, {len(questions)} remaining.")

        if not questions:
            self.stdout.write(self.style.SUCCESS("Nothing left to classify."))
            if not options["dry_run"]:
                self._apply_jsonl(output_path, dry_run=False)
            return

        self.stdout.write(
            f"Classifying {len(questions)} questions with {options['model']} "
            f"(workers={options['workers']})…"
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        mode = "a" if options["resume"] and output_path.exists() else "w"
        write_lock = Lock()

        ok = 0
        errors = 0
        with output_path.open(mode, encoding="utf-8") as handle:
            with ThreadPoolExecutor(max_workers=max(1, options["workers"])) as pool:
                futures = {
                    pool.submit(
                        self._classify_one,
                        client,
                        options["model"],
                        q,
                    ): q
                    for q in questions
                }
                for future in as_completed(futures):
                    question = futures[future]
                    try:
                        result = future.result()
                    except Exception as exc:  # noqa: BLE001 — surface per-question failure
                        errors += 1
                        self.stderr.write(f"FAIL Q{question.pk}: {exc}")
                        continue
                    line = json.dumps(result, ensure_ascii=False) + "\n"
                    with write_lock:
                        handle.write(line)
                        handle.flush()
                    ok += 1
                    if ok % 25 == 0 or ok == len(questions):
                        self.stdout.write(f"  {ok}/{len(questions)} ok ({errors} errors)")

        self.stdout.write(self.style.SUCCESS(f"Wrote {ok} results to {output_path} ({errors} errors)"))
        if options["dry_run"]:
            self.stdout.write("Dry-run: DB unchanged.")
            return
        self._apply_jsonl(output_path, dry_run=False)

    def _client(self, profile: str, region: str):
        session = boto3.Session(profile_name=profile, region_name=region)
        return session.client(
            "bedrock-runtime",
            config=Config(read_timeout=120, retries={"max_attempts": 4}),
        )

    def _classify_one(self, client, model_id: str, question: Question) -> dict:
        payload = question_payload(question)
        user_prompt = build_user_prompt(payload)
        last_error: Exception | None = None
        for attempt in range(4):
            try:
                response = client.converse(
                    modelId=model_id,
                    system=[{"text": SYSTEM_PROMPT}],
                    messages=[{"role": "user", "content": [{"text": user_prompt}]}],
                    inferenceConfig={"maxTokens": 800, "temperature": 0},
                )
                text = "".join(
                    block.get("text", "")
                    for block in response.get("output", {}).get("message", {}).get("content", [])
                )
                parsed = parse_model_json(text)
                topic_code = str(parsed.get("topic_code", "")).strip()
                if topic_code not in VALID_CODES:
                    raise ValueError(f"invalid topic_code={topic_code!r}")

                existing_explanation = question.explanation or ""
                explanation = resolve_explanation(
                    existing=existing_explanation,
                    model_explanation=str(parsed.get("explanation_user") or ""),
                )
                usage = response.get("usage") or {}
                return {
                    "question_id": question.pk,
                    "exam_number": question.exam_number,
                    "question_number": question.question_number,
                    "source": question.source,
                    "topic_code": topic_code,
                    "topic_label": resolve_topic_label(topic_code, parsed.get("topic_label")),
                    "confidence": parsed.get("confidence"),
                    "runners_up": parsed.get("runners_up") or [],
                    "analysis": parsed.get("analysis") or "",
                    "explanation_user": explanation,
                    "explanation_was_existing": bool(existing_explanation.strip()),
                    "model_id": model_id,
                    "usage": {
                        "input_tokens": usage.get("inputTokens"),
                        "output_tokens": usage.get("outputTokens"),
                    },
                    "raw": parsed,
                }
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                time.sleep(1.5 * (attempt + 1))
        raise RuntimeError(f"Bedrock failed after retries: {last_error}")

    def _iter_jsonl_rows(self, path: Path):
        raw = path.read_bytes().replace(b"\x00", b"")
        for line_no, line in enumerate(raw.decode("utf-8", errors="replace").splitlines(), start=1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                self.stderr.write(f"Skip bad JSONL line {line_no}: {exc}")

    def _load_done_ids(self, path: Path) -> set[int]:
        ids: set[int] = set()
        for row in self._iter_jsonl_rows(path):
            try:
                ids.add(int(row["question_id"]))
            except (KeyError, TypeError, ValueError):
                continue
        return ids

    def _apply_jsonl(self, path: Path, *, dry_run: bool) -> None:
        if not path.exists():
            raise CommandError(f"JSONL not found: {path}")

        updates: dict[int, dict] = {}
        for row in self._iter_jsonl_rows(path):
            try:
                qid = int(row["question_id"])
            except (KeyError, TypeError, ValueError):
                continue
            updates[qid] = row

        if not updates:
            raise CommandError(f"No valid classification rows in {path}")

        applied = 0
        with transaction.atomic():
            for question in Question.objects.filter(pk__in=updates.keys()):
                row = updates[question.pk]
                topic_code = row["topic_code"]
                if topic_code not in VALID_CODES:
                    continue
                question.capsule_topic = resolve_topic_label(topic_code, row.get("topic_label"))
                question.explanation = resolve_explanation(
                    existing=question.explanation or "",
                    model_explanation=row.get("explanation_user") or "",
                )
                if not dry_run:
                    question.save(update_fields=["capsule_topic", "explanation"])
                applied += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"{'Would update' if dry_run else 'Updated'} {applied} questions "
                f"from {path} ({len(updates)} rows in file)"
            )
        )
