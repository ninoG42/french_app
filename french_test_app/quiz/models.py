from django.conf import settings
from django.db import models


class Question(models.Model):
    class Category(models.TextChoices):
        ORTHOGRAPHE = "orthographe", "Orthographe"
        SYNTAXE = "syntaxe", "Syntaxe"
        VOCABULAIRE = "vocabulaire", "Vocabulaire"

    class Source(models.TextChoices):
        EXAM = "exam", "Examen"
        CAPSULE = "capsule", "Capsule"
        SERIE = "serie", "Série"

    source = models.CharField(max_length=10, choices=Source.choices, default=Source.EXAM)
    capsule_topic = models.CharField(max_length=100, blank=True, default="")
    exam_number = models.PositiveSmallIntegerField(help_text="Exam example number (1-6)")
    question_number = models.PositiveSmallIntegerField(help_text="Question number within the exam (1-60)")
    category = models.CharField(max_length=20, choices=Category.choices)
    question_text = models.TextField()
    option_1 = models.TextField()
    option_2 = models.TextField()
    option_3 = models.TextField()
    option_4 = models.TextField()
    option_a = models.TextField(default="Aucune")
    option_t = models.TextField(default="Toutes")
    correct_answer = models.CharField(
        max_length=1,
        help_text="One of: 1, 2, 3, 4, A, T",
    )
    explanation = models.TextField(blank=True, default="")
    reference_text = models.TextField(
        blank=True,
        default="",
        help_text="Reference text for vocabulary questions",
    )

    class Meta:
        unique_together = ("exam_number", "question_number")
        ordering = ["exam_number", "question_number"]

    def __str__(self):
        return f"Exam {self.exam_number} - Q{self.question_number} ({self.category})"


class AnswerLog(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="answer_logs")
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="answer_logs")
    selected_answer = models.CharField(max_length=1, help_text="One of: 1, 2, 3, 4, A, T, S (skip)")
    is_correct = models.BooleanField()
    answered_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-answered_at"]

    def __str__(self):
        return f"{self.user} - Q{self.question.question_number} ({'✓' if self.is_correct else '✗'})"


class UserQuestionProgress(models.Model):
    class Strength(models.TextChoices):
        UNSEEN = "unseen", "Unseen"
        WEAK = "weak", "Weak"
        MEDIUM = "medium", "Medium"
        STRONG = "strong", "Strong"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="question_progress")
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="user_progress")
    times_shown = models.PositiveIntegerField(default=0)
    times_correct = models.PositiveIntegerField(default=0)
    strength = models.CharField(max_length=10, choices=Strength.choices, default=Strength.UNSEEN)
    last_seen = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ("user", "question")

    def __str__(self):
        return f"{self.user} - {self.question} ({self.strength})"

    @property
    def correct_rate(self):
        if self.times_shown == 0:
            return 0.0
        return self.times_correct / self.times_shown

    def update_strength(self):
        if self.times_shown == 0:
            self.strength = self.Strength.UNSEEN
        elif self.times_shown < 5:
            if self.correct_rate >= 0.5:
                self.strength = self.Strength.MEDIUM
            else:
                self.strength = self.Strength.WEAK
        elif self.correct_rate >= 0.8:
            self.strength = self.Strength.STRONG
        elif self.correct_rate >= 0.5:
            self.strength = self.Strength.MEDIUM
        else:
            self.strength = self.Strength.WEAK
        self.save(update_fields=["strength"])


class Resource(models.Model):
    class MaterialType(models.TextChoices):
        CAPSULE = "capsule", "Capsule"
        THEORY = "theorie", "Théorie"
        EXERCISE = "exercice", "Exercice"
        CORRIGE = "corrige", "Corrigé"
        MISE_EN_SITUATION = "mise_en_situation", "Mise en situation"
        OTHER = "autre", "Autre"

    title = models.CharField(max_length=200)
    capsule_number = models.PositiveSmallIntegerField(null=True, blank=True)
    topic = models.CharField(max_length=100)
    category = models.CharField(
        max_length=20,
        choices=Question.Category.choices,
        default=Question.Category.ORTHOGRAPHE,
    )
    material_type = models.CharField(
        max_length=20,
        choices=MaterialType.choices,
        default=MaterialType.OTHER,
    )
    pdf_file = models.FileField(upload_to="resources/")
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["category", "order", "capsule_number", "material_type"]

    def __str__(self):
        prefix = f"Capsule {self.capsule_number} - " if self.capsule_number else ""
        return f"{prefix}{self.title}"
