"""Load grammar resource PDFs from aux_data/ into the Resource model."""

import re
import shutil
from pathlib import Path

from django.conf import settings
from django.core.files import File
from django.core.management.base import BaseCommand

from french_test_app.quiz.models import Resource

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

FILENAME_RULES = [
    # Capsule slides: "Capsule 3_PPT.pdf"
    (re.compile(r"^Capsule (\d+\w?)_PPT", re.I), "capsule", None),
    # Mise en situation: "3.1_Mise en situation.pdf"
    (re.compile(r"^(\d+)\.\d+_Mise en situation", re.I), "mise_en_situation", None),
    # Numbered theory: "2.2_Théorie.pdf", "3.2_Théorie.pdf"
    (re.compile(r"^(\d+)\.\d+_Th[ée]orie", re.I), "theorie", None),
    # Numbered exercises: "7.2.Quelque_exercices.pdf"
    (re.compile(r"^(\d+)\.\d+\.?\w*_?[Ee]xercices?", re.I), "exercice", None),
    # Homophones exercises
    (re.compile(r"^Homophones\d*\.pdf", re.I), "exercice", ("Les homophones", 3)),
    # Accents
    (re.compile(r"^Accents?_.*th[ée]orie", re.I), "theorie", ("Les accents", 16)),
    (re.compile(r"^Accents?_.*exercice", re.I), "exercice", ("Les accents", 16)),
    (re.compile(r"^Ortho_rect", re.I), "theorie", ("Les accents", 16)),
    # Accord participe passé
    (re.compile(r"^Accord part.*Th[ée]orie", re.I), "theorie", ("Participe passé", 9)),
    (re.compile(r"^Accord part.*Corrig", re.I), "corrige", ("Participe passé", 9)),
    (re.compile(r"^Accord part.*Exercice", re.I), "exercice", ("Participe passé", 9)),
    (re.compile(r"^Algorithme participe", re.I), "theorie", ("Participe passé avec être", 11)),
    # Accord du verbe
    (re.compile(r"^Accord verbe", re.I), "exercice", ("Accord du verbe", 2)),
    # Adverbes
    (re.compile(r"^Adverbes_th[ée]orie", re.I), "theorie", ("Les adverbes", 13)),
    (re.compile(r"^Adverbes_exercices\d*_Corrig", re.I), "corrige", ("Les adverbes", 13)),
    (re.compile(r"^Adverbes_exercices", re.I), "exercice", ("Les adverbes", 13)),
    # Pronoms relatifs
    (re.compile(r"^Les pronoms relatifs.*th[ée]orie", re.I), "theorie", ("Les pronoms relatifs", 14)),
    (re.compile(r"^Les pronoms relatifs.*corrig", re.I), "corrige", ("Les pronoms relatifs", 14)),
    (re.compile(r"^Les pronoms relatifs.*exercice", re.I), "exercice", ("Les pronoms relatifs", 14)),
    (re.compile(r"^Exercices_dont_corrig", re.I), "corrige", ("Les pronoms relatifs", 14)),
    (re.compile(r"^Exercices_dont\.pdf", re.I), "exercice", ("Les pronoms relatifs", 14)),
    (re.compile(r"^Th[ée]orie_dont", re.I), "theorie", ("Les pronoms relatifs", 14)),
    # Pronoms (général)
    (re.compile(r"^Pronoms.*th[ée]orie", re.I), "theorie", ("Les pronoms (difficultés)", 15)),
    (re.compile(r"^Pronoms.*classe", re.I), "theorie", ("Les pronoms (difficultés)", 15)),
    (re.compile(r"^Pronoms exercices\d*_ ?Corrig", re.I), "corrige", ("Les pronoms (difficultés)", 15)),
    (re.compile(r"^Pronoms exercices", re.I), "exercice", ("Les pronoms (difficultés)", 15)),
    # Discours indirect
    (re.compile(r"^Th[ée]orie disc direct", re.I), "theorie", ("Discours indirect", 17)),
    (re.compile(r"^Exercices disc direct.*corrig", re.I), "corrige", ("Discours indirect", 17)),
    (re.compile(r"^Exercices disc direct", re.I), "exercice", ("Discours indirect", 17)),
    # Ruptures syntaxiques
    (re.compile(r"^Ruptures syntaxiques\s*\.pdf", re.I), "theorie", ("Les ruptures syntaxiques", 19)),
    (re.compile(r"^Ruptures.*(C|c)orrig", re.I), "corrige", ("Les ruptures syntaxiques", 19)),
    (re.compile(r"^Ruptures.*exercice", re.I), "exercice", ("Les ruptures syntaxiques", 19)),
    # Participe présent / adjectif verbal
    (re.compile(r"^Participe present.*th[ée]orie", re.I), "theorie", ("Participe présent / adjectif verbal", 12)),
    (re.compile(r"^Participe present.*exercice", re.I), "exercice", ("Participe présent / adjectif verbal", 12)),
    (re.compile(r"^Corrig[ée] Participe present", re.I), "corrige", ("Participe présent / adjectif verbal", 12)),
    # Tout / quelque / même / tel
    (re.compile(r"^Tout quelque|^Corrig[ée]_Tout quelque|^Tout meme", re.I), "exercice", ("Tout / quelque / même / tel", 8)),
    # Virgule / ponctuation
    (re.compile(r"^Virgule\.(pdf)$", re.I), "theorie", ("La ponctuation", 20)),
    (re.compile(r"^Point-virgule", re.I), "theorie", ("La ponctuation", 20)),
    (re.compile(r"^Virgule exercice\d*_Corrig", re.I), "corrige", ("La ponctuation", 20)),
    (re.compile(r"^Virgule exercice", re.I), "exercice", ("La ponctuation", 20)),
    # Verbes conjugaison
    (re.compile(r"^Verbes.*(Corrig|corrig)", re.I), "corrige", ("La conjugaison (difficultés)", 21)),
    (re.compile(r"^Verbes", re.I), "exercice", ("La conjugaison (difficultés)", 21)),
    (re.compile(r"^Imp[ée]ratif", re.I), "theorie", ("La conjugaison (difficultés)", 21)),
    (re.compile(r"^Les verbes pronominaux.*corrig", re.I), "corrige", ("La conjugaison (difficultés)", 21)),
    (re.compile(r"^Les verbes pronominaux", re.I), "exercice", ("La conjugaison (difficultés)", 21)),
    (re.compile(r"^Liste.*(verbes pron|essentiellement)", re.I), "theorie", ("La conjugaison (difficultés)", 21)),
    # Nombres / chiffres
    (re.compile(r"^Chiffres_", re.I), "theorie", ("Les nombres et chiffres", 18)),
    # Orthographe rectifiée
    (re.compile(r"^Miniguide_orthographe", re.I), "theorie", ("Les accents", 16)),
    # Exam-capsule mapping
    (re.compile(r"^Questions examen", re.I), "autre", ("Correspondance questions-capsules", None)),
    # Series
    (re.compile(r"^S[ée]rie [AB]", re.I), "exercice", ("Exercices généraux", None)),
]

SKIP_EXTENSIONS = {".docx"}


def classify_file(filename: str):
    """Return (material_type, topic, capsule_number) for a filename, or None to skip."""
    ext = Path(filename).suffix.lower()
    if ext in SKIP_EXTENSIONS:
        return None
    if ext != ".pdf":
        return None

    for pattern, mat_type, override in FILENAME_RULES:
        m = pattern.search(filename)
        if not m:
            continue

        if override:
            topic, caps_num = override
            return mat_type, topic, caps_num

        caps_str = m.group(1)
        caps_num = int(re.match(r"\d+", caps_str).group())
        topic = CAPSULE_TOPICS.get(caps_num, f"Capsule {caps_str}")
        return mat_type, topic, caps_num

    return None


class Command(BaseCommand):
    help = "Load grammar resource PDFs from aux_data/ into the database"

    def add_arguments(self, parser):
        parser.add_argument(
            "--source",
            default="aux_data",
            help="Path to the folder containing resource PDFs",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Delete all existing resources before loading",
        )

    def handle(self, *args, **options):
        source_dir = Path(options["source"])
        if not source_dir.exists():
            self.stderr.write(self.style.ERROR(f"Source folder not found: {source_dir}"))
            return

        if options["clear"]:
            deleted, _ = Resource.objects.all().delete()
            self.stdout.write(f"Deleted {deleted} existing resources")

        media_dest = Path(settings.MEDIA_ROOT) / "resources"
        media_dest.mkdir(parents=True, exist_ok=True)

        created = 0
        skipped = 0
        unmatched = []

        for filepath in sorted(source_dir.iterdir()):
            if filepath.is_dir():
                continue

            result = classify_file(filepath.name)
            if result is None:
                if filepath.suffix.lower() == ".pdf":
                    unmatched.append(filepath.name)
                else:
                    skipped += 1
                continue

            mat_type, topic, caps_num = result
            category = CAPSULE_CATEGORIES.get(caps_num, "orthographe") if caps_num else "orthographe"

            dest_path = media_dest / filepath.name
            if not dest_path.exists():
                shutil.copy2(filepath, dest_path)

            title = filepath.stem.replace("_", " ")

            with open(dest_path, "rb") as f:
                obj, was_created = Resource.objects.update_or_create(
                    title=title,
                    defaults={
                        "capsule_number": caps_num,
                        "topic": topic,
                        "category": category,
                        "material_type": mat_type,
                        "pdf_file": File(f, name=f"resources/{filepath.name}"),
                        "order": caps_num or 99,
                    },
                )

            if was_created:
                created += 1

        if unmatched:
            self.stdout.write(self.style.WARNING(f"Unmatched PDFs: {', '.join(unmatched)}"))

        self.stdout.write(
            self.style.SUCCESS(
                f"Loaded {created} resources ({skipped} non-PDF files skipped)"
            )
        )
