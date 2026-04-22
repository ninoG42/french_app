"""
Reusable PDF parsing utilities for OP001 QCM exams.

Extracts questions, options, and explanations from HEP Vaud
questionnaire and corrigé PDFs.
"""

import re
import tempfile

import fitz  # PyMuPDF


def extract_text_with_bold(pdf_file) -> str:
    """
    Extract text from a PDF, wrapping bold spans in <b> tags.

    Accepts a file path (str) or a Django UploadedFile / file-like object.
    """
    if isinstance(pdf_file, str):
        doc = fitz.open(pdf_file)
    else:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            for chunk in pdf_file.chunks():
                tmp.write(chunk)
            tmp.flush()
            doc = fitz.open(tmp.name)

    parts = []
    for page in doc:
        page_dict = page.get_text("dict")
        for block in page_dict["blocks"]:
            if "lines" not in block:
                continue
            for line in block["lines"]:
                for span in line["spans"]:
                    text = span["text"]
                    is_bold = bool(span["flags"] & 16) or "Bold" in span.get("font", "")
                    if is_bold and text.strip():
                        parts.append(f"<b>{text}</b>")
                    else:
                        parts.append(text)
                parts.append("\n")
    doc.close()
    return "".join(parts)


def extract_plain_text(pdf_file) -> str:
    """Extract plain text from a PDF (no formatting)."""
    if isinstance(pdf_file, str):
        doc = fitz.open(pdf_file)
    else:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            for chunk in pdf_file.chunks():
                tmp.write(chunk)
            tmp.flush()
            doc = fitz.open(tmp.name)

    text = "\n".join(page.get_text() for page in doc)
    doc.close()
    return text


def split_into_questions(text: str) -> dict[int, str]:
    """Split text into per-question chunks keyed by question number."""
    pattern = re.compile(r"(?=(?:<b>)?Question\s+(\d+)\s*(?:</b>)?\s*\n)")
    splits = list(pattern.finditer(text))
    result = {}
    for i, m in enumerate(splits):
        q_num = int(m.group(1))
        start = m.start()
        end = splits[i + 1].start() if i + 1 < len(splits) else len(text)
        result[q_num] = text[start:end].strip()
    return result


def parse_question_chunk(chunk: str) -> dict:
    """Parse a single question chunk into structured data."""
    lines = chunk.split("\n")

    header_match = re.match(r"(?:<b>)?Question\s+\d+\s*(?:</b>)?", lines[0])
    if header_match:
        lines = lines[1:]

    text_lines = []
    options = {}
    explanation_lines = []
    phase = "text"

    option_pattern = re.compile(r"^([1-4])\s*[-–]\s*(.+)")
    option_a_pattern = re.compile(r"^A\s*[-–]\s*(.+)")
    option_t_pattern = re.compile(r"^T\s*[-–—]\s*(.+)")

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        i += 1

        if not line:
            continue

        if phase == "text":
            opt_m = option_pattern.match(line)
            opt_a = option_a_pattern.match(line)
            if opt_m:
                phase = "options"
                options[opt_m.group(1)] = opt_m.group(2).strip()
                continue
            elif opt_a:
                phase = "options"
                options["A"] = opt_a.group(1).strip()
                continue
            else:
                text_lines.append(line)
                continue

        if phase == "options":
            opt_m = option_pattern.match(line)
            opt_a = option_a_pattern.match(line)
            opt_t = option_t_pattern.match(line)
            if opt_m:
                options[opt_m.group(1)] = opt_m.group(2).strip()
            elif opt_a:
                options["A"] = opt_a.group(1).strip()
            elif opt_t:
                options["T"] = opt_t.group(1).strip()
                phase = "explanation"
            elif options:
                last_key = list(options.keys())[-1]
                options[last_key] += " " + line
            continue

        if phase == "explanation":
            explanation_lines.append(line)

    question_text = re.sub(r"\s+", " ", " ".join(text_lines)).strip()
    question_text = re.sub(r"<b>\s+", "<b>", question_text)
    question_text = re.sub(r"\s+</b>", "</b>", question_text)

    explanation = re.sub(r"\s+", " ", " ".join(explanation_lines)).strip()

    return {
        "question_text": question_text,
        "option_1": options.get("1", ""),
        "option_2": options.get("2", ""),
        "option_3": options.get("3", ""),
        "option_4": options.get("4", ""),
        "option_a": options.get("A", "Aucune"),
        "option_t": options.get("T", "Toutes"),
        "explanation": explanation,
    }


def extract_reference_text(pdf_file) -> str:
    """Extract the annexe/reference text for vocabulaire questions."""
    text = extract_plain_text(pdf_file)

    for marker in [
        "Les questions suivantes portent sur le vocabulaire",
        "Veuillez vous référer",
    ]:
        pos = text.find(marker)
        if pos != -1:
            break
    else:
        return ""

    q41_pos = text.find("Question 41", pos)
    if q41_pos == -1:
        return ""

    for marker in ["ANNEXE", "Annexe", "Texte"]:
        annexe_pos = text.find(marker, q41_pos)
        if annexe_pos != -1:
            ref = text[annexe_pos:].strip()
            return re.sub(r"\s+", " ", ref)[:8000]

    last_t = max(text.rfind("T -"), text.rfind("T –"))
    if last_t != -1:
        next_nl = text.find("\n", last_t)
        if next_nl != -1:
            remaining = text[next_nl:].strip()
            if remaining and not remaining.startswith("Question"):
                return re.sub(r"\s+", " ", remaining)[:8000]

    return ""


def parse_exam_pdfs(
    corrige_file,
    questionnaire_file=None,
    *,
    sections=("syntaxe", "orthographe", "vocabulaire"),
    answers=None,
):
    """
    Parse a corrigé PDF (and optionally a questionnaire PDF) into a list
    of question dicts ready to be saved as Question model instances.

    Args:
        corrige_file: Corrigé PDF (path or UploadedFile).
        questionnaire_file: Questionnaire PDF for reference text extraction.
        sections: Tuple of 3 category names for Q1-20, Q21-40, Q41-60.
        answers: Dict mapping question_number -> correct answer code,
                 or None to leave answers blank.

    Returns:
        List of dicts with keys matching Question model fields (minus exam_number).
    """
    corrige_text = extract_text_with_bold(corrige_file)
    chunks = split_into_questions(corrige_text)

    ref_text = ""
    if questionnaire_file:
        ref_text = extract_reference_text(questionnaire_file)

    results = []
    for q_num in sorted(chunks.keys()):
        parsed = parse_question_chunk(chunks[q_num])

        if q_num <= 20:
            category = sections[0]
        elif q_num <= 40:
            category = sections[1]
        else:
            category = sections[2]

        correct = ""
        if answers and q_num in answers:
            correct = answers[q_num]

        results.append({
            "question_number": q_num,
            "category": category,
            "question_text": parsed["question_text"],
            "option_1": parsed["option_1"],
            "option_2": parsed["option_2"],
            "option_3": parsed["option_3"],
            "option_4": parsed["option_4"],
            "option_a": parsed["option_a"],
            "option_t": parsed["option_t"],
            "correct_answer": correct,
            "explanation": parsed["explanation"],
            "reference_text": ref_text if category == "vocabulaire" else "",
        })

    return results
