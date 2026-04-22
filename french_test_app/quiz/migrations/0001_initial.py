import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Question",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("exam_number", models.PositiveSmallIntegerField(help_text="Exam example number (1-6)")),
                ("question_number", models.PositiveSmallIntegerField(help_text="Question number within the exam (1-60)")),
                ("category", models.CharField(choices=[("orthographe", "Orthographe"), ("syntaxe", "Syntaxe"), ("vocabulaire", "Vocabulaire")], max_length=20)),
                ("question_text", models.TextField()),
                ("option_1", models.TextField()),
                ("option_2", models.TextField()),
                ("option_3", models.TextField()),
                ("option_4", models.TextField()),
                ("option_a", models.TextField(default="Aucune")),
                ("option_t", models.TextField(default="Toutes")),
                ("correct_answer", models.CharField(help_text="One of: 1, 2, 3, 4, A, T", max_length=1)),
                ("explanation", models.TextField(blank=True, default="")),
                ("reference_text", models.TextField(blank=True, default="", help_text="Reference text for vocabulary questions")),
            ],
            options={
                "ordering": ["exam_number", "question_number"],
                "unique_together": {("exam_number", "question_number")},
            },
        ),
        migrations.CreateModel(
            name="UserQuestionProgress",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("times_shown", models.PositiveIntegerField(default=0)),
                ("times_correct", models.PositiveIntegerField(default=0)),
                ("strength", models.CharField(choices=[("unseen", "Unseen"), ("weak", "Weak"), ("medium", "Medium"), ("strong", "Strong")], default="unseen", max_length=10)),
                ("last_seen", models.DateTimeField(blank=True, null=True)),
                ("question", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="user_progress", to="quiz.question")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="question_progress", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "unique_together": {("user", "question")},
            },
        ),
        migrations.CreateModel(
            name="AnswerLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("selected_answer", models.CharField(help_text="One of: 1, 2, 3, 4, A, T, S (skip)", max_length=1)),
                ("is_correct", models.BooleanField()),
                ("answered_at", models.DateTimeField(auto_now_add=True)),
                ("question", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="answer_logs", to="quiz.question")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="answer_logs", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["-answered_at"],
            },
        ),
    ]
