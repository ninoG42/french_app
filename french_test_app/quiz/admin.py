from django.contrib import admin

from .models import AnswerLog, Question, UserQuestionProgress


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("exam_number", "question_number", "category", "correct_answer")
    list_filter = ("exam_number", "category")
    search_fields = ("question_text",)


@admin.register(AnswerLog)
class AnswerLogAdmin(admin.ModelAdmin):
    list_display = ("user", "question", "selected_answer", "is_correct", "answered_at")
    list_filter = ("is_correct",)


@admin.register(UserQuestionProgress)
class UserQuestionProgressAdmin(admin.ModelAdmin):
    list_display = ("user", "question", "times_shown", "times_correct", "strength")
    list_filter = ("strength",)
