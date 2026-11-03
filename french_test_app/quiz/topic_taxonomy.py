"""Topic taxonomy and Bedrock prompts for OP001 capsule classification."""

from __future__ import annotations

import json
import re
from html import unescape

# code -> (label stored in Question.capsule_topic, short scope)
TAXONOMY: dict[str, tuple[str, str]] = {
    "classes_fonctions": (
        "Classes et fonctions grammaticales",
        "Nature et fonction des mots",
    ),
    "accord_sujet_verbe": ("Accord du verbe", "Accord du verbe avec le sujet"),
    "homophones": ("Les homophones", "Mots de même son, graphies différentes"),
    "chaque_chacun": ("Chaque / chacun", "Emploi et accord de chaque/chacun"),
    "leur": ("Leur", "Leur / leurs (déterminant ou pronom)"),
    "meme": ("Même", "Même / mêmes"),
    "quelque": ("Quelque", "Quelque / quel que / quelques"),
    "tout": ("Tout", "Tout / toute / tous / toutes"),
    "pp_sans_auxiliaire": (
        "Participe passé sans auxiliaire",
        "Participe passé sans auxiliaire",
    ),
    "pp_avec_avoir": (
        "Participe passé avec avoir",
        "Participe passé avec avoir",
    ),
    "pp_avec_etre": (
        "Participe passé avec être",
        "Participe passé avec être / pronominaux",
    ),
    "participe_present": (
        "Participe présent / adjectif verbal",
        "Formes en -ant",
    ),
    "adverbes": ("Les adverbes", "Formation et emploi des adverbes"),
    "pronoms_relatifs": ("Les pronoms relatifs", "qui, que, dont, lequel…"),
    "pronoms": ("Les pronoms (difficultés)", "Pronoms personnels / démonstratifs / etc."),
    "accents": ("Les accents", "Accents, cédille, tréma"),
    "discours_indirect": (
        "Discours indirect",
        "Transformation / concordance au discours rapporté",
    ),
    "nombres": ("Les nombres et chiffres", "Écriture et accord des nombres"),
    "ruptures_syntaxiques": (
        "Les ruptures syntaxiques",
        "Constructions syntaxiques cassées",
    ),
    "ponctuation": ("La ponctuation", "Signes de ponctuation"),
    "conjugaison": (
        "La conjugaison (difficultés)",
        "Temps, modes, formes verbales",
    ),
    "difficulte_orthographiques": (
        "Les difficultés orthographiques",
        "Orthographe hors capsules précises",
    ),
    "concordance_temps": ("Concordance des temps", "Enchaînement des temps"),
    "connecteurs": ("Connecteurs", "Articulateurs logiques"),
    "gentiles": ("Gentilés", "Noms/adjectifs d'habitants"),
    "negation": ("La négation", "Marques et portée de la négation"),
    "autre": ("Autre", "Hors capsules / ne correspond à aucun sujet"),
}

VALID_CODES = frozenset(TAXONOMY.keys())

SYSTEM_PROMPT = """You are an expert French linguistics tutor specializing in the HEP Vaud OP001 exam (Appui de français). You classify multiple-choice questions into exactly ONE topic from a fixed capsule taxonomy.

You will receive:
- the allowed labels in <taxonomy> tags (code | label | short scope)
- one question in <question> tags

Your task:
1. Read the stem, options, correct answer, and explanation carefully.
2. Decide which SINGLE taxonomy code best matches the grammatical point tested.
3. Prefer the most specific capsule. Do not invent labels.
4. If the question does not clearly match any taxonomy topic, return topic_code "autre". Do not force a weak match.

Before classifying, analyze in the "analysis" field:
1. What linguistic phenomenon is being tested?
2. Which 2–3 labels could plausibly match?
3. Why the chosen label wins over the runners-up?

TOPIC DISAMBIGUATION — MANDATORY:
- Relative pronouns (dont, qui, que, lequel…) → pronoms_relatifs (not pronoms, not connecteurs)
- Personal / demonstrative / possessive pronoun traps → pronoms
- Homophones (a/à, ou/où, ce/se…) → homophones (leur as determiner/pronoun agreement trap → leur)
- tout / toute / tous / toutes → tout
- quelque / quel que / quelques → quelque
- même / mêmes → meme
- chaque / chacun / chacune → chaque_chacun
- Past participle WITHOUT auxiliary → pp_sans_auxiliaire
- Past participle with avoir → pp_avec_avoir
- Past participle with être / pronominal verbs → pp_avec_etre
- participe présent vs adjectif verbal (-ant) → participe_present
- Verb–subject agreement (number/person) → accord_sujet_verbe
- Tense/mood form choice → conjugaison
- Sequence of tenses across clauses → concordance_temps
- Accent / cédille / tréma spelling → accents
- Discourse reported speech → discours_indirect
- Numbers written in letters → nombres
- Broken syntax / anacoluthe → ruptures_syntaxiques
- Commas, colons, quotation marks… → ponctuation
- Word classes / syntactic functions → classes_fonctions
- Broad spelling traps not covered above → difficulte_orthographiques
- Logical connectors → connecteurs
- Place-of-origin adjectives → gentiles
- ne…pas / ne…que / double negation → negation

Always provide "explanation_user":
- If the question already has a non-empty explanation, copy it EXACTLY (100% reuse). Do not rewrite, shorten, translate, or improve it.
- If explanation is empty/missing, write ONE new simple French sentence (max 150 words, aim under 30) that explains the point tested for the student.
- Do not mention taxonomy codes or this classification task.

Never return more than one code. Never return null."""


def taxonomy_block() -> str:
    lines = [
        f"{code} | {label} | {scope}" for code, (label, scope) in TAXONOMY.items()
    ]
    return "<taxonomy>\n" + "\n".join(lines) + "\n</taxonomy>"


_HTML_TAG_RE = re.compile(r"<[^>]+>")


def strip_html(text: str) -> str:
    return unescape(_HTML_TAG_RE.sub("", text or "")).strip()


def build_user_prompt(payload: dict) -> str:
    return f"""{taxonomy_block()}

<question>
{json.dumps(payload, ensure_ascii=False, indent=2)}
</question>

Classify this question into exactly one taxonomy code.

Output format (required):
Respond with ONLY valid JSON — no markdown fences, no text before or after.
Use this shape:
{{
  "analysis": string,
  "question_id": number,
  "topic_code": string,
  "topic_label": string,
  "confidence": number,
  "runners_up": [string],
  "explanation_user": string
}}"""


def question_payload(question) -> dict:
    return {
        "id": question.pk,
        "exam_number": question.exam_number,
        "question_number": question.question_number,
        "source": question.source,
        "existing_category": question.category,
        "existing_capsule_topic": question.capsule_topic or "",
        "question_text": strip_html(question.question_text),
        "options": {
            "1": question.option_1,
            "2": question.option_2,
            "3": question.option_3,
            "4": question.option_4,
            "A": question.option_a,
            "T": question.option_t,
        },
        "correct_answer": question.correct_answer,
        "explanation": question.explanation or "",
    }


def parse_model_json(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return json.loads(cleaned)


def resolve_explanation(*, existing: str, model_explanation: str) -> str:
    """Reuse an existing explanation 100%; only invent when blank."""
    if existing and existing.strip():
        return existing
    return (model_explanation or "").strip()


def resolve_topic_label(topic_code: str, model_label: str | None = None) -> str:
    if topic_code in TAXONOMY:
        return TAXONOMY[topic_code][0]
    return (model_label or topic_code or "Autre").strip()
