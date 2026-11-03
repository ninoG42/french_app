from django.contrib import admin

from .models import AnswerLog, CourseGroup, Module, Question, Resource, UserQuestionProgress


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("module", "source", "exam_number", "question_number", "category", "correct_answer", "teacher_checked")
    list_filter = ("source", "module", "exam_number", "category", "teacher_checked")
    list_editable = ("teacher_checked",)
    search_fields = ("question_text", "module__title")


@admin.register(Module)
class ModuleAdmin(admin.ModelAdmin):
    list_display = ("title", "category", "is_published", "created_by", "created_at")
    list_filter = ("is_published", "category")
    search_fields = ("title",)


@admin.register(AnswerLog)
class AnswerLogAdmin(admin.ModelAdmin):
    list_display = ("user", "question", "selected_answer", "is_correct", "answered_at")
    list_filter = ("is_correct",)


@admin.register(UserQuestionProgress)
class UserQuestionProgressAdmin(admin.ModelAdmin):
    list_display = ("user", "question", "times_shown", "times_correct", "strength")
    list_filter = ("strength",)


@admin.register(Resource)
class ResourceAdmin(admin.ModelAdmin):
    list_display = ("title", "capsule_number", "topic", "category", "material_type")
    list_filter = ("category", "material_type", "topic")


@admin.register(CourseGroup)
class CourseGroupAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)
    filter_horizontal = ("teachers", "students")
