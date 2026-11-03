"""Limited inline HTML for teacher-edited question énoncés."""

from __future__ import annotations

from html import escape
from html.parser import HTMLParser

ALLOWED_INLINE = frozenset({"b", "i", "em", "strong"})
ALLOWED_VOID = frozenset({"br"})
ALLOWED_TAGS = ALLOWED_INLINE | ALLOWED_VOID

QUESTION_TEXT_HELP = (
    "Mise en forme limitée via la barre d’outils : gras, italique, "
    "guillemets français « … ». Le formatage s’affiche directement dans l’éditeur."
)

OPTION_TEXT_HELP = (
    "Même mise en forme que l’énoncé : gras, italique, guillemets « … » "
    "(recliquer sur « » retire les guillemets)."
)

RICH_TEXT_FIELDS = (
    "question_text",
    "option_1",
    "option_2",
    "option_3",
    "option_4",
    "option_a",
    "option_t",
    "explanation",
    "reference_text",
)


class _QuestionHtmlSanitizer(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._stack: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:  # noqa: ARG002
        name = tag.lower()
        if name in ALLOWED_VOID:
            self._parts.append("<br>")
            return
        if name in ALLOWED_INLINE:
            self._stack.append(name)
            self._parts.append(f"<{name}>")

    def handle_endtag(self, tag: str) -> None:
        name = tag.lower()
        if name not in ALLOWED_INLINE:
            return
        if name in self._stack:
            while self._stack:
                opened = self._stack.pop()
                self._parts.append(f"</{opened}>")
                if opened == name:
                    break

    def handle_data(self, data: str) -> None:
        self._parts.append(escape(data, quote=False))

    def handle_startendtag(self, tag: str, attrs) -> None:  # noqa: ARG002
        if tag.lower() in ALLOWED_VOID:
            self._parts.append("<br>")

    def close(self) -> None:
        while self._stack:
            self._parts.append(f"</{self._stack.pop()}>")
        super().close()

    def result(self) -> str:
        return "".join(self._parts)


def sanitize_question_html(text: str | None) -> str:
    """Keep only b/i/em/strong/br; escape everything else as plain text."""
    if text is None:
        return ""
    if not text:
        return text
    parser = _QuestionHtmlSanitizer()
    parser.feed(text)
    parser.close()
    return parser.result()


def convert_straight_quotes_to_guillemets(text: str | None) -> tuple[str, int, bool]:
    """Replace ASCII ``"..."`` pairs with French guillemets ``« ... »``.

    Returns ``(new_text, replacements, unpaired)``. Opening quotes become ``« ``,
    closing quotes become `` »``. Already-correct ``« »`` are left untouched.
    """
    if not text or '"' not in text:
        return text or "", 0, False
    parts: list[str] = []
    open_next = True
    replacements = 0
    for ch in text:
        if ch != '"':
            parts.append(ch)
            continue
        parts.append("« " if open_next else " »")
        open_next = not open_next
        replacements += 1
    unpaired = replacements % 2 == 1
    return "".join(parts), replacements, unpaired

