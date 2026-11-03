from collections import Counter

from django import forms
from django.db.models import Max

from .importers import parse_question_payload
from .models import Module
from .models import Question
from .progress_breakdown import EXAMEN_SERIE_NUMBER, SERIE_A_EXAM_NUMBER
from .rich_text import OPTION_TEXT_HELP
from .rich_text import QUESTION_TEXT_HELP
from .rich_text import RICH_TEXT_FIELDS
from .rich_text import sanitize_question_html
from .topic_taxonomy import TAXONOMY

# Extra thèmes shown after the capsule taxonomy (Autre + séries enseignants).
SERIE_TOPIC_LABELS = {
    SERIE_A_EXAM_NUMBER: "Série A",
    EXAMEN_SERIE_NUMBER: "Examen",
}
OTHER_TOPIC_LABELS = ("Autre", *SERIE_TOPIC_LABELS.values())


def capsule_topic_choices(*, include_blank=True, extra: str = ""):
    """Dropdown: capsule taxonomy, then Autre / séries, plus any orphan DB topics."""
    taxonomy_labels = {
        label for code, (label, _scope) in TAXONOMY.items() if code != "autre"
    }
    other_labels = set(OTHER_TOPIC_LABELS)
    db_labels = set(
        Question.objects.exclude(capsule_topic="")
        .order_by("capsule_topic")
        .values_list("capsule_topic", flat=True)
        .distinct()
    )
    if extra:
        db_labels.add(extra)

    capsule_group = sorted(taxonomy_labels, key=str.casefold)
    other_group = list(OTHER_TOPIC_LABELS)
    leftover = sorted(
        (db_labels - taxonomy_labels - other_labels),
        key=str.casefold,
    )

    choices = [("", "— Aucun —")] if include_blank else []
    choices.append(("Thèmes de capsules", [(label, label) for label in capsule_group]))
    choices.append(("Autres / séries", [(label, label) for label in other_group]))
    if leftover:
        choices.append(("Autres thèmes", [(label, label) for label in leftover]))
    return choices


def _exam_number_for_capsule_topic(topic: str, *, keep=None):
    """Reuse the pack number already tied to this thème, or allocate the next one."""
    if keep is not None:
        return keep
    existing = list(
        Question.objects.filter(source=Question.Source.CAPSULE, capsule_topic=topic)
        .exclude(exam_number__isnull=True)
        .values_list("exam_number", flat=True)
    )
    if existing:
        return Counter(existing).most_common(1)[0][0]
    max_n = (
        Question.objects.filter(source=Question.Source.CAPSULE).aggregate(m=Max("exam_number"))["m"]
        or 99
    )
    return max(int(max_n) + 1, 100)


class ModuleForm(forms.ModelForm):
    class Meta:
        model = Module
        fields = ["title", "description", "category", "is_published"]


SERIE_NUMBER_CHOICES = [
    (EXAMEN_SERIE_NUMBER, "Examen (n° 8)"),
    (SERIE_A_EXAM_NUMBER, "Série A (n° 7)"),
]

QUESTION_NUMBER_MAX = 60


def _available_question_number_choices(exam_number, *, keep=None, exclude_pk=None):
    """Only numbers not already used in this ensemble (keep current when editing)."""
    if exam_number is None:
        return [("", "— Choisissez d’abord l’exemple, la série ou le thème —")]
    qs = Question.objects.filter(module__isnull=True, exam_number=exam_number)
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    taken = set(qs.values_list("question_number", flat=True))
    free = [n for n in range(1, QUESTION_NUMBER_MAX + 1) if n not in taken]
    if keep is not None and keep not in free:
        free = sorted({*free, int(keep)})
    if not free:
        return [("", "— Aucun numéro libre (1–60) —")]
    return [(n, f"Q{n}") for n in free]


class QuestionForm(forms.ModelForm):
    capsule_topic = forms.ChoiceField(
        required=False,
        label="Thème",
        help_text="Sujet pédagogique (capsules OP001, Autre, ou série).",
    )
    question_number = forms.TypedChoiceField(
        coerce=int,
        empty_value=None,
        label="Numéro de question",
        help_text="Uniquement les numéros encore libres dans cet ensemble.",
    )

    class Meta:
        model = Question
        fields = [
            "source",
            "exam_number",
            "question_number",
            "capsule_topic",
            "category",
            "question_text",
            "option_1",
            "option_2",
            "option_3",
            "option_4",
            "option_a",
            "option_t",
            "correct_answer",
            "explanation",
            "reference_text",
            "teacher_checked",
        ]
        labels = {
            "teacher_checked": "Contrôlée et correcte (enseignant)",
            "exam_number": "Numéro d’ensemble",
        }
        help_texts = {
            "teacher_checked": "Cochez lorsque l’énoncé et la réponse ont été vérifiés.",
            "question_text": QUESTION_TEXT_HELP,
            "option_1": OPTION_TEXT_HELP,
            "option_2": OPTION_TEXT_HELP,
            "option_3": OPTION_TEXT_HELP,
            "option_4": OPTION_TEXT_HELP,
            "option_a": OPTION_TEXT_HELP,
            "option_t": OPTION_TEXT_HELP,
            "explanation": OPTION_TEXT_HELP,
            "reference_text": OPTION_TEXT_HELP,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        current_topic = ""
        source = None
        current_exam = None
        current_qnum = None
        exclude_pk = None
        if self.instance and self.instance.pk:
            current_topic = self.instance.capsule_topic or ""
            source = self.instance.source
            current_exam = self.instance.exam_number
            current_qnum = self.instance.question_number
            exclude_pk = self.instance.pk
        if self.data.get("source"):
            source = self.data.get("source")
        elif self.initial.get("source"):
            source = self.initial.get("source")

        if self.data.get("capsule_topic") is not None:
            current_topic = self.data.get("capsule_topic") or current_topic
        elif self.initial.get("capsule_topic"):
            current_topic = self.initial.get("capsule_topic")

        raw_exam = self.data.get("exam_number")
        if raw_exam not in (None, ""):
            try:
                current_exam = int(raw_exam)
            except (TypeError, ValueError):
                pass
        elif self.initial.get("exam_number") not in (None, ""):
            current_exam = int(self.initial["exam_number"])

        self.fields["capsule_topic"].choices = capsule_topic_choices(extra=current_topic)
        if current_topic:
            self.initial.setdefault("capsule_topic", current_topic)

        # Modules are not used in the question bank UI.
        self.fields["source"].choices = [
            choice for choice in Question.Source.choices if choice[0] != Question.Source.MODULE
        ]
        self._configure_set_number_field(source, current_exam)

        exam_for_qnums = current_exam
        if source == Question.Source.CAPSULE and current_topic:
            exam_for_qnums = _exam_number_for_capsule_topic(
                current_topic,
                keep=current_exam if exclude_pk else None,
            )
        self.fields["question_number"].choices = _available_question_number_choices(
            exam_for_qnums,
            keep=current_qnum,
            exclude_pk=exclude_pk,
        )
        if current_qnum is not None:
            self.initial.setdefault("question_number", current_qnum)
        elif exam_for_qnums is not None and self.fields["question_number"].choices:
            first = self.fields["question_number"].choices[0][0]
            if first != "" and "question_number" not in self.initial:
                self.initial["question_number"] = first

    def _sanitize_rich_text_fields(self, cleaned_data):
        for name in RICH_TEXT_FIELDS:
            if name in cleaned_data and cleaned_data[name] is not None:
                cleaned_data[name] = sanitize_question_html(cleaned_data[name])
        return cleaned_data

    def _configure_set_number_field(self, source, current_exam=None):
        field = self.fields["exam_number"]
        field.required = source not in {Question.Source.MODULE, Question.Source.CAPSULE, None}
        if source == Question.Source.SERIE:
            field.label = "Numéro de série"
            field.help_text = "Choisissez la série. L’app étudiante affiche le n° 8 comme « Examen »."
            field.widget = forms.Select(choices=SERIE_NUMBER_CHOICES)
        elif source == Question.Source.CAPSULE:
            # Pack number is derived from the thème — no separate UI field.
            field.label = "Numéro d’ensemble"
            field.help_text = ""
            field.required = False
            field.widget = forms.HiddenInput()
            if current_exam is not None:
                self.initial.setdefault("exam_number", current_exam)
        elif source == Question.Source.EXAM:
            field.label = "Numéro d’exemple"
            field.help_text = "Exemple d’examen OP001 (généralement 1 à 6)."
            field.widget = forms.NumberInput(attrs={"min": 1})
        else:
            field.label = "Numéro d’ensemble"
            field.help_text = "Non utilisé pour les questions de module."
            field.required = False
            field.widget = forms.HiddenInput()

    def clean(self):
        cleaned_data = super().clean()
        cleaned_data = self._sanitize_rich_text_fields(cleaned_data)
        source = cleaned_data.get("source")
        exam_number = cleaned_data.get("exam_number")
        question_number = cleaned_data.get("question_number")
        topic = cleaned_data.get("capsule_topic") or ""
        cleaned_data["module"] = None
        if source == Question.Source.MODULE:
            self.add_error("source", "Les modules ne sont plus proposés dans cette interface.")
            return cleaned_data
        if source == Question.Source.CAPSULE:
            if not topic:
                self.add_error("capsule_topic", "Choisissez un thème.")
                return cleaned_data
            keep = self.instance.exam_number if self.instance and self.instance.pk else None
            exam_number = _exam_number_for_capsule_topic(topic, keep=keep)
            cleaned_data["exam_number"] = exam_number
        elif not exam_number:
            if source == Question.Source.SERIE:
                self.add_error("exam_number", "Le numéro de série est requis.")
            else:
                self.add_error("exam_number", "Le numéro d’exemple est requis.")
            return cleaned_data
        if exam_number and question_number:
            clash = Question.objects.filter(
                module__isnull=True,
                exam_number=exam_number,
                question_number=question_number,
            )
            if self.instance and self.instance.pk:
                clash = clash.exclude(pk=self.instance.pk)
            if clash.exists():
                self.add_error(
                    "question_number",
                    "Ce numéro de question existe déjà pour cet ensemble.",
                )
        return cleaned_data


class QuestionCreateForm(QuestionForm):
    """Same as QuestionForm; question_number remains required (no auto-numbering)."""


class ModuleQuestionCreateForm(forms.ModelForm):
    """Question create form for the legacy module detail page only."""

    question_number = forms.TypedChoiceField(
        coerce=int,
        label="Numéro de question",
        help_text="Uniquement les numéros encore libres dans ce module.",
    )

    class Meta:
        model = Question
        fields = [
            "source",
            "module",
            "exam_number",
            "question_number",
            "capsule_topic",
            "category",
            "question_text",
            "option_1",
            "option_2",
            "option_3",
            "option_4",
            "option_a",
            "option_t",
            "correct_answer",
            "explanation",
            "reference_text",
        ]
        help_texts = {
            "question_text": QUESTION_TEXT_HELP,
            "option_1": OPTION_TEXT_HELP,
            "option_2": OPTION_TEXT_HELP,
            "option_3": OPTION_TEXT_HELP,
            "option_4": OPTION_TEXT_HELP,
            "option_a": OPTION_TEXT_HELP,
            "option_t": OPTION_TEXT_HELP,
            "explanation": OPTION_TEXT_HELP,
            "reference_text": OPTION_TEXT_HELP,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["exam_number"].required = False
        self.fields["capsule_topic"].required = False
        module = None
        if self.data.get("module"):
            module = Module.objects.filter(pk=self.data.get("module")).first()
        elif self.initial.get("module"):
            module = self.initial["module"]
        taken = set()
        if module is not None:
            taken = set(module.questions.values_list("question_number", flat=True))
        free = [n for n in range(1, QUESTION_NUMBER_MAX + 1) if n not in taken]
        self.fields["question_number"].choices = [(n, f"Q{n}") for n in free] or [
            ("", "— Aucun numéro libre —")
        ]
        if free and "question_number" not in self.initial:
            self.initial["question_number"] = free[0]

    def clean(self):
        cleaned_data = super().clean()
        for name in RICH_TEXT_FIELDS:
            if name in cleaned_data and cleaned_data[name] is not None:
                cleaned_data[name] = sanitize_question_html(cleaned_data[name])
        return cleaned_data


class ModuleImportForm(forms.Form):
    json_file = forms.FileField(required=False, help_text="Importer un fichier JSON")
    json_text = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 10}),
        help_text="Ou coller le JSON directement",
    )

    def clean(self):
        cleaned_data = super().clean()
        json_file = cleaned_data.get("json_file")
        json_text = (cleaned_data.get("json_text") or "").strip()
        if not json_file and not json_text:
            raise forms.ValidationError("Fournissez un fichier JSON ou du texte JSON.")
        if json_file:
            json_text = json_file.read().decode("utf-8")
        rows, errors = parse_question_payload(json_text)
        if errors:
            error_text = "; ".join(f"Ligne {err.row}: {err.message}" for err in errors[:10])
            raise forms.ValidationError(error_text)
        cleaned_data["rows"] = rows
        cleaned_data["json_text"] = json_text
        return cleaned_data
