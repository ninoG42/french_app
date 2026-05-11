"""Generate QCM questions from capsule exercise+corrigé PDFs via Gemini.

For each capsule topic, extracts text from exercise and corrigé PDFs,
sends the content to Gemini to generate multiple-choice questions in
OP001 format, and saves them to the Question model.
"""

import json
import logging
import time
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from french_test_app.quiz.models import Question, Resource

logger = logging.getLogger(__name__)

CAPSULE_TOPICS = {
    1: "Classes et fonctions grammaticales",
    2: "Accord du verbe",
    3: "Les homophones",
    4: "Chaque / chacun",
    5: "Leur",
    6: "Même",
    7: "Quelque",
    8: "Tout",
    9: "Participe passé sans auxiliaire",
    10: "Participe passé avec avoir",
    11: "Participe passé avec être",
    12: "Participe présent / adjectif verbal",
    13: "Les adverbes",
    14: "Les pronoms relatifs",
    15: "Les pronoms (difficultés)",
    16: "Les accents",
    17: "Discours indirect",
    18: "Les nombres et chiffres",
    19: "Les ruptures syntaxiques",
    20: "La ponctuation",
    21: "La conjugaison (difficultés)",
}

CAPSULE_CATEGORIES = {
    1: "orthographe",
    2: "orthographe",
    3: "orthographe",
    4: "orthographe",
    5: "orthographe",
    6: "orthographe",
    7: "orthographe",
    8: "orthographe",
    9: "orthographe",
    10: "orthographe",
    11: "orthographe",
    12: "orthographe",
    13: "orthographe",
    14: "syntaxe",
    15: "syntaxe",
    16: "orthographe",
    17: "syntaxe",
    18: "orthographe",
    19: "syntaxe",
    20: "syntaxe",
    21: "orthographe",
}


def _extract_pdf_text(filepath: str) -> str:
    """Extract plain text from a PDF using PyMuPDF."""
    import fitz

    doc = fitz.open(filepath)
    text = "\n".join(page.get_text() for page in doc)
    doc.close()
    return text


def _collect_topic_texts(source_dir: Path) -> dict[int, dict]:
    """Collect exercise and corrigé texts for each capsule topic from the Resource model.

    Falls back to scanning source_dir if resources aren't loaded yet.
    """
    topics = {}

    for caps_num, topic_name in CAPSULE_TOPICS.items():
        resources = Resource.objects.filter(
            capsule_number=caps_num,
            material_type__in=["exercice", "corrige", "theorie"],
        )

        exercise_texts = []
        corrige_texts = []
        theory_texts = []

        for res in resources:
            try:
                pdf_path = res.pdf_file.path
                text = _extract_pdf_text(pdf_path)
                if not text.strip():
                    continue
                if res.material_type == "exercice":
                    exercise_texts.append(text[:4000])
                elif res.material_type == "corrige":
                    corrige_texts.append(text[:4000])
                elif res.material_type == "theorie":
                    theory_texts.append(text[:3000])
            except Exception:
                logger.warning("Could not read %s", res.pdf_file)

        if not exercise_texts and not theory_texts:
            continue

        topics[caps_num] = {
            "topic": topic_name,
            "category": CAPSULE_CATEGORIES[caps_num],
            "exercises": exercise_texts,
            "corriges": corrige_texts,
            "theory": theory_texts,
        }

    return topics


def _generate_qcm_for_topic(
    caps_num: int,
    topic_data: dict,
    api_key: str,
    num_questions: int = 8,
) -> list[dict]:
    """Call Gemini to generate QCM questions for a topic."""
    from google import genai

    client = genai.Client(api_key=api_key)

    exercise_block = "\n\n---\n\n".join(topic_data["exercises"][:3])
    corrige_block = "\n\n---\n\n".join(topic_data["corriges"][:2])
    theory_block = "\n\n---\n\n".join(topic_data["theory"][:1])

    content_parts = []
    if theory_block:
        content_parts.append(f"=== THÉORIE ===\n{theory_block}")
    if exercise_block:
        content_parts.append(f"=== EXERCICES ===\n{exercise_block}")
    if corrige_block:
        content_parts.append(f"=== CORRIGÉ ===\n{corrige_block}")

    content = "\n\n".join(content_parts)
    if len(content) > 15000:
        content = content[:15000]

    prompt = f"""Tu es un professeur de français expert préparant des QCM pour l'examen OP001 (HEP Vaud).

Thème : {topic_data['topic']} (Capsule {caps_num})
Catégorie : {topic_data['category']}

Voici du matériel pédagogique sur ce thème (théorie, exercices et corrigés) :

{content}

À partir de ce matériel, génère exactement {num_questions} questions à choix multiples (QCM) au format OP001.

RÈGLES STRICTES :
- Chaque question doit avoir exactement 4 options numérotées 1 à 4
- Une seule réponse correcte par question (parmi 1, 2, 3, 4)
- Les questions doivent tester la maîtrise de la règle grammaticale du thème
- Inclus une explication courte pour chaque question
- Les questions doivent être variées et couvrir différents aspects du thème
- Niveau de difficulté adapté à l'examen OP001

Réponds UNIQUEMENT en JSON valide, un tableau d'objets avec cette structure exacte :
[
  {{
    "question_text": "Complétez la phrase suivante...",
    "option_1": "première option",
    "option_2": "deuxième option",
    "option_3": "troisième option",
    "option_4": "quatrième option",
    "correct_answer": "2",
    "explanation": "Explication de la règle..."
  }}
]"""

    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
            )
            text = response.text.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1]
                text = text.rsplit("```", 1)[0]
            return json.loads(text)
        except Exception:
            logger.exception(
                "Gemini generation failed for capsule %d (attempt %d/3)",
                caps_num, attempt + 1,
            )
            if attempt < 2:
                time.sleep(10 * (attempt + 1))
    return []


class Command(BaseCommand):
    help = "Generate QCM questions from capsule materials via Gemini"

    def add_arguments(self, parser):
        parser.add_argument(
            "--source",
            default="aux_data",
            help="Path to folder containing resource PDFs",
        )
        parser.add_argument(
            "--capsule",
            type=int,
            help="Generate for a specific capsule number only",
        )
        parser.add_argument(
            "--num-questions",
            type=int,
            default=8,
            help="Number of questions to generate per topic (default: 8)",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Delete existing capsule-generated questions before generating",
        )

    def handle(self, *args, **options):
        api_key = settings.GEMINI_API_KEY
        if not api_key:
            self.stderr.write(self.style.ERROR("GEMINI_API_KEY not set."))
            return

        source_dir = Path(options["source"])
        num_questions = options["num_questions"]

        if options["clear"]:
            deleted, _ = Question.objects.filter(source=Question.Source.CAPSULE).delete()
            self.stdout.write(f"Deleted {deleted} existing capsule questions")

        self.stdout.write("Collecting exercise texts from resources...")
        topic_texts = _collect_topic_texts(source_dir)

        if options["capsule"]:
            caps = options["capsule"]
            if caps not in topic_texts:
                self.stderr.write(self.style.ERROR(
                    f"No exercise materials found for capsule {caps}"
                ))
                return
            topic_texts = {caps: topic_texts[caps]}

        self.stdout.write(f"Found materials for {len(topic_texts)} topics")

        total_created = 0
        for caps_num, topic_data in sorted(topic_texts.items()):
            exam_number = 100 + caps_num
            existing = Question.objects.filter(
                exam_number=exam_number, source=Question.Source.CAPSULE
            ).count()
            if existing and not options["clear"]:
                self.stdout.write(
                    f"  Capsule {caps_num}: {topic_data['topic']} "
                    f"-- {existing} questions exist, skipping"
                )
                continue

            self.stdout.write(
                f"  Capsule {caps_num}: {topic_data['topic']}..."
            )

            generated = _generate_qcm_for_topic(
                caps_num, topic_data, api_key, num_questions
            )
            if not generated:
                self.stderr.write(self.style.WARNING(
                    f"    No questions generated for capsule {caps_num}"
                ))
                continue

            exam_number = 100 + caps_num
            created = 0
            for i, q in enumerate(generated, start=1):
                correct = q.get("correct_answer", "")
                if correct not in ("1", "2", "3", "4", "A", "T"):
                    continue

                _, was_created = Question.objects.update_or_create(
                    exam_number=exam_number,
                    question_number=i,
                    defaults={
                        "source": Question.Source.CAPSULE,
                        "capsule_topic": topic_data["topic"],
                        "category": topic_data["category"],
                        "question_text": q.get("question_text", ""),
                        "option_1": q.get("option_1", ""),
                        "option_2": q.get("option_2", ""),
                        "option_3": q.get("option_3", ""),
                        "option_4": q.get("option_4", ""),
                        "option_a": "Aucune",
                        "option_t": "Toutes",
                        "correct_answer": correct,
                        "explanation": q.get("explanation", ""),
                        "reference_text": "",
                    },
                )
                if was_created:
                    created += 1

            self.stdout.write(self.style.SUCCESS(
                f"    {created} questions created ({len(generated)} generated)"
            ))
            total_created += created

            time.sleep(8)

        self.stdout.write(self.style.SUCCESS(
            f"\nTotal: {total_created} capsule questions created"
        ))
