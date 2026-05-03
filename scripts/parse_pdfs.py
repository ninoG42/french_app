"""
Parse OP001 exam PDFs and their corrigés into a JSON fixture for Django.

Each exam has 60 questions in 3 sections of 20:
  - syntaxe, orthographe, vocabulaire (order varies by exam)

Uses the corrigé PDFs as primary source (they contain both
the questions AND explanations). Correct answers come from
a verified lookup table.
"""

import json
import re
import sys
from pathlib import Path

import fitz  # PyMuPDF


# Verified correct answers for all 6 exams (from corrigé analysis).
CORRECT_ANSWERS = {
    1: {
        1: "3", 2: "A", 3: "2", 4: "2", 5: "T", 6: "T", 7: "A",
        8: "1", 9: "2", 10: "4", 11: "T", 12: "1", 13: "2", 14: "4",
        15: "3", 16: "3", 17: "A", 18: "T", 19: "4", 20: "2",
        21: "A", 22: "1", 23: "4", 24: "1", 25: "4", 26: "1", 27: "3",
        28: "1", 29: "3", 30: "4", 31: "1", 32: "2", 33: "3", 34: "2",
        35: "2", 36: "A", 37: "3", 38: "4", 39: "1", 40: "2",
        41: "3", 42: "2", 43: "T", 44: "4", 45: "4", 46: "2", 47: "4",
        48: "1", 49: "1", 50: "4", 51: "2", 52: "2", 53: "2", 54: "3",
        55: "4", 56: "3", 57: "2", 58: "A", 59: "3", 60: "3",
    },
    2: {
        1: "3", 2: "4", 3: "2", 4: "4", 5: "3", 6: "4", 7: "1",
        8: "3", 9: "3", 10: "A", 11: "1", 12: "3", 13: "2", 14: "1",
        15: "3", 16: "2", 17: "A", 18: "2", 19: "4", 20: "1",
        21: "1", 22: "2", 23: "4", 24: "4", 25: "T", 26: "3", 27: "1",
        28: "A", 29: "A", 30: "3", 31: "3", 32: "1", 33: "3", 34: "T",
        35: "1", 36: "4", 37: "A", 38: "2", 39: "1", 40: "T",
        41: "1", 42: "1", 43: "3", 44: "A", 45: "A", 46: "3", 47: "4",
        48: "1", 49: "4", 50: "2", 51: "3", 52: "4", 53: "A", 54: "3",
        55: "1", 56: "2", 57: "2", 58: "4", 59: "1", 60: "1",
    },
    3: {
        1: "1", 2: "A", 3: "4", 4: "4", 5: "T", 6: "2", 7: "1",
        8: "2", 9: "3", 10: "T", 11: "2", 12: "3", 13: "2", 14: "A",
        15: "4", 16: "2", 17: "2", 18: "A", 19: "3", 20: "1",
        21: "3", 22: "A", 23: "2", 24: "4", 25: "3", 26: "1", 27: "T",
        28: "3", 29: "2", 30: "3", 31: "1", 32: "3", 33: "2", 34: "3",
        35: "2", 36: "A", 37: "4", 38: "3", 39: "3", 40: "1",
        41: "1", 42: "T", 43: "A", 44: "4", 45: "3", 46: "1", 47: "2",
        48: "4", 49: "2", 50: "4", 51: "1", 52: "3", 53: "1", 54: "2",
        55: "1", 56: "4", 57: "1", 58: "4", 59: "4", 60: "A",
    },
    4: {
        1: "2", 2: "A", 3: "1", 4: "3", 5: "2", 6: "T", 7: "3",
        8: "2", 9: "1", 10: "4", 11: "1", 12: "4", 13: "3", 14: "A",
        15: "A", 16: "4", 17: "3", 18: "A", 19: "2", 20: "2",
        21: "4", 22: "T", 23: "3", 24: "4", 25: "4", 26: "3", 27: "3",
        28: "4", 29: "2", 30: "2", 31: "2", 32: "2", 33: "3", 34: "1",
        35: "4", 36: "2", 37: "4", 38: "4", 39: "3", 40: "3",
        41: "2", 42: "T", 43: "1", 44: "3", 45: "3", 46: "1", 47: "1",
        48: "4", 49: "3", 50: "1", 51: "A", 52: "2", 53: "4", 54: "4",
        55: "2", 56: "T", 57: "4", 58: "3", 59: "4", 60: "2",
    },
    5: {
        1: "1", 2: "3", 3: "A", 4: "1", 5: "4", 6: "3", 7: "2",
        8: "2", 9: "2", 10: "3", 11: "2", 12: "1", 13: "2", 14: "2",
        15: "3", 16: "T", 17: "4", 18: "3", 19: "A", 20: "1",
        21: "4", 22: "1", 23: "3", 24: "T", 25: "2", 26: "A", 27: "A",
        28: "1", 29: "3", 30: "1", 31: "4", 32: "2", 33: "3", 34: "T",
        35: "3", 36: "A", 37: "2", 38: "1", 39: "A", 40: "4",
        41: "3", 42: "4", 43: "1", 44: "1", 45: "1", 46: "3", 47: "3",
        48: "2", 49: "4", 50: "A", 51: "2", 52: "A", 53: "2", 54: "4",
        55: "3", 56: "1", 57: "4", 58: "2", 59: "A", 60: "3",
    },
    6: {
        1: "2", 2: "3", 3: "4", 4: "4", 5: "2", 6: "1", 7: "2",
        8: "4", 9: "1", 10: "1", 11: "3", 12: "A", 13: "2", 14: "3",
        15: "1", 16: "A", 17: "4", 18: "T", 19: "3", 20: "1",
        21: "3", 22: "A", 23: "T", 24: "1", 25: "4", 26: "4", 27: "3",
        28: "4", 29: "1", 30: "T", 31: "2", 32: "1", 33: "1", 34: "2",
        35: "3", 36: "3", 37: "2", 38: "2", 39: "4", 40: "T",
        41: "1", 42: "T", 43: "3", 44: "2", 45: "3", 46: "2", 47: "3",
        48: "2", 49: "4", 50: "4", 51: "1", 52: "1", 53: "2", 54: "T",
        55: "A", 56: "3", 57: "2", 58: "A", 59: "3", 60: "1",
    },
}

# Section ordering per exam (determined from questionnaire analysis).
# Exam 1: Q1-20 syntaxe, Q21-40 orthographe, Q41-60 vocabulaire
# Exam 2: Q1-20 orthographe, Q21-40 syntaxe, Q41-60 vocabulaire
# Exam 3: Q1-20 syntaxe, Q21-40 orthographe, Q41-60 vocabulaire
# Exam 4: Q1-20 syntaxe, Q21-40 orthographe, Q41-60 vocabulaire
# Exam 5: Q1-20 orthographe, Q21-40 syntaxe, Q41-60 vocabulaire
# Exam 6: Q1-20 orthographe, Q21-40 syntaxe, Q41-60 vocabulaire
SECTION_ORDER = {
    1: ("syntaxe", "orthographe", "vocabulaire"),
    2: ("orthographe", "syntaxe", "vocabulaire"),
    3: ("syntaxe", "orthographe", "vocabulaire"),
    4: ("syntaxe", "orthographe", "vocabulaire"),
    5: ("orthographe", "syntaxe", "vocabulaire"),
    6: ("orthographe", "syntaxe", "vocabulaire"),
}


def get_category(exam_number: int, question_number: int) -> str:
    sections = SECTION_ORDER[exam_number]
    if question_number <= 20:
        return sections[0]
    elif question_number <= 40:
        return sections[1]
    else:
        return sections[2]


def extract_full_text(pdf_path: str, preserve_bold: bool = False) -> str:
    """Extract text from PDF pages, optionally wrapping bold spans in <b> tags."""
    doc = fitz.open(pdf_path)
    if not preserve_bold:
        return "\n".join(page.get_text() for page in doc)

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
    return "".join(parts)


def split_into_questions(text: str) -> dict[int, str]:
    """Split corrigé text into per-question chunks."""
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

    # Remove the "Question N" header (may have bold tags)
    header_match = re.match(r"(?:<b>)?Question\s+\d+\s*(?:</b>)?", lines[0])
    if header_match:
        lines = lines[1:]

    text_lines = []
    options = {}
    explanation_lines = []
    phase = "text"  # text -> options -> explanation

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
                continue
            elif opt_a:
                options["A"] = opt_a.group(1).strip()
                continue
            elif opt_t:
                options["T"] = opt_t.group(1).strip()
                phase = "explanation"
                continue
            else:
                # Continuation of previous option text
                if options:
                    last_key = list(options.keys())[-1]
                    options[last_key] += " " + line
                continue

        if phase == "explanation":
            explanation_lines.append(line)

    question_text = " ".join(text_lines)
    question_text = re.sub(r"\s+", " ", question_text).strip()
    # Clean up spaces around bold tags
    question_text = re.sub(r"<b>\s+", "<b>", question_text)
    question_text = re.sub(r"\s+</b>", "</b>", question_text)

    explanation = " ".join(explanation_lines)
    explanation = re.sub(r"\s+", " ", explanation).strip()

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


def extract_reference_text(questionnaire_path: str) -> str:
    """Extract the annexe/reference text for vocabulaire questions."""
    text = extract_full_text(questionnaire_path)
    markers = [
        "Les questions suivantes portent sur le vocabulaire",
        "Veuillez vous référer",
    ]
    # Find the vocabulaire section start
    vocab_start = -1
    for marker in markers:
        pos = text.find(marker)
        if pos != -1:
            vocab_start = pos
            break

    if vocab_start == -1:
        return ""

    # Find "Question 41" to get the reference text location
    q41_pos = text.find("Question 41", vocab_start)
    if q41_pos == -1:
        return ""

    # The reference text (annexe) is typically at the end of the document
    # after the last question. Look for "ANNEXE" or the text block after Q60.
    annexe_markers = ["ANNEXE", "Annexe", "Texte"]
    annexe_start = -1
    for marker in annexe_markers:
        pos = text.find(marker, q41_pos)
        if pos != -1:
            annexe_start = pos
            break

    # If no annexe marker found, look after the T option of the last question
    if annexe_start == -1:
        last_t = text.rfind("T -")
        if last_t == -1:
            last_t = text.rfind("T –")
        if last_t != -1:
            # Find end of last option line
            next_nl = text.find("\n", last_t)
            if next_nl != -1:
                remaining = text[next_nl:].strip()
                if remaining and not remaining.startswith("Question"):
                    return remaining

    if annexe_start != -1:
        return text[annexe_start:].strip()

    return ""


def build_fixture(pdf_dir: str, output_path: str):
    """Build the complete Django fixture JSON from all 6 exams."""
    fixture = []
    pk = 1

    for exam_num in range(1, 7):
        q_pdf = Path(pdf_dir) / f"exemple{exam_num}-OP001-hep-vaud.pdf"
        c_pdf = Path(pdf_dir) / f"exemple{exam_num}-corrige-OP001-hep-vaud.pdf"

        print(f"Processing exam {exam_num}...")

        # Extract reference text for vocabulaire from questionnaire PDF
        ref_text = extract_reference_text(str(q_pdf))
        if ref_text:
            ref_text = re.sub(r"\s+", " ", ref_text).strip()
            if len(ref_text) > 8000:
                ref_text = ref_text[:8000] + "..."

        # Parse questions+options from questionnaire (clean, no corrections)
        quest_text = extract_full_text(str(q_pdf), preserve_bold=True)
        quest_chunks = split_into_questions(quest_text)

        # Parse explanations from corrigé
        corrige_text = extract_full_text(str(c_pdf), preserve_bold=True)
        corrige_chunks = split_into_questions(corrige_text)

        answers = CORRECT_ANSWERS[exam_num]

        parsed_count = 0
        for q_num in range(1, 61):
            quest_parsed = (
                parse_question_chunk(quest_chunks[q_num])
                if q_num in quest_chunks
                else None
            )
            corrige_parsed = (
                parse_question_chunk(corrige_chunks[q_num])
                if q_num in corrige_chunks
                else None
            )

            if quest_parsed and quest_parsed["option_1"]:
                source = quest_parsed
            elif corrige_parsed:
                print(f"  WARNING: Q{q_num} missing from questionnaire, using corrigé")
                source = corrige_parsed
            else:
                print(f"  WARNING: Q{q_num} not found in either PDF")
                source = {
                    "question_text": f"[Question {q_num} - parsing failed]",
                    "option_1": "", "option_2": "", "option_3": "", "option_4": "",
                    "option_a": "Aucune", "option_t": "Toutes",
                }

            explanation = corrige_parsed["explanation"] if corrige_parsed else ""
            parsed_count += 1

            category = get_category(exam_num, q_num)
            is_vocab = category == "vocabulaire"

            fixture.append({
                "model": "quiz.question",
                "pk": pk,
                "fields": {
                    "exam_number": exam_num,
                    "question_number": q_num,
                    "category": category,
                    "question_text": source["question_text"],
                    "option_1": source["option_1"],
                    "option_2": source["option_2"],
                    "option_3": source["option_3"],
                    "option_4": source["option_4"],
                    "option_a": source["option_a"],
                    "option_t": source["option_t"],
                    "correct_answer": answers[q_num],
                    "explanation": explanation,
                    "reference_text": ref_text if is_vocab else "",
                },
            })
            pk += 1

        print(f"  Parsed {parsed_count}/60 questions")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(fixture, f, ensure_ascii=False, indent=2)

    print(f"\nWrote {len(fixture)} questions to {output_path}")


if __name__ == "__main__":
    pdf_dir = sys.argv[1] if len(sys.argv) > 1 else "pdfs"
    output = sys.argv[2] if len(sys.argv) > 2 else "french_test_app/fixtures/questions.json"
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    build_fixture(pdf_dir, output)
