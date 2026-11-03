"""Create a fictional class in the isolated local demo database."""
import random
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from french_test_app.quiz.models import AnswerLog, CourseGroup, Question, UserQuestionProgress


class Command(BaseCommand):
    help = "Crée une classe fictive, uniquement avec config.settings.demo."

    @transaction.atomic
    def handle(self, *args, **options):
        if not getattr(settings, "HEPL_DEMO", False) or not settings.DEBUG:
            raise CommandError("Utilisez exclusivement --settings=config.settings.demo.")
        if CourseGroup.objects.exists():
            raise CommandError("La démonstration est déjà préparée. Aucun compte modifié.")
        questions = list(Question.objects.order_by("category", "exam_number", "question_number"))
        if not questions:
            raise CommandError("Importez d’abord le catalogue de questions.")
        User = get_user_model()
        password = secrets.token_urlsafe(12)
        teacher = User.objects.create_user(email="prof.demo@example.test", name="Enseignante · Démonstration", password=password)
        teacher.user_permissions.add(*Permission.objects.filter(
            content_type__app_label="quiz", codename__in=["add_question", "change_question"],
        ))
        group = CourseGroup.objects.create(name="Appui de français · Groupe pilote")
        group.teachers.add(teacher)
        # A balanced selection from the real catalogue; all student outcomes are fictitious.
        selection = []
        for category, _ in Question.Category.choices:
            selection += [q for q in questions if q.category == category][:12]
        rng = random.Random(42)
        now = timezone.now()
        for i in range(1, 13):
            student = User.objects.create_user(
                email=f"etudiant{i:02d}.demo@example.test", name=f"Étudiant {i:02d}",
                password=password if i == 1 else None,
            )
            group.students.add(student)
            if i == 12:
                continue
            for j, question in enumerate(selection[:max(8, len(selection) - i)]):
                correct = 0
                count = rng.randint(1, 7)
                for attempt in range(count):
                    success = rng.random() < min(.95, .25 + (j % 5) * .13 + attempt * .06)
                    correct += int(success)
                    selected = question.correct_answer if success else next(c for c in "1234" if c != question.correct_answer)
                    log = AnswerLog.objects.create(user=student, question=question, selected_answer=selected, is_correct=success)
                    occurred = now - timedelta(days=max(0, 13 - attempt * 2 - i % 3), minutes=j * 7 + i)
                    AnswerLog.objects.filter(pk=log.pk).update(answered_at=occurred)
                progress = UserQuestionProgress.objects.create(user=student, question=question, times_shown=count, times_correct=correct, last_seen=occurred)
                progress.update_strength()
        self.stdout.write(self.style.SUCCESS("Classe de démonstration créée (12 étudiants fictifs)."))
        self.stdout.write(f"Enseignante : prof.demo@example.test\nÉtudiant : etudiant01.demo@example.test\nMot de passe des deux comptes : {password}")
