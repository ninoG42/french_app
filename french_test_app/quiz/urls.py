from django.urls import path

from . import views, teacher, documents

app_name = "quiz"
urlpatterns = [
    path("ressources/<int:resource_id>/", documents.viewer, name="document"),
    path("ressources/<int:resource_id>/page/<int:page>/", documents.page_image, name="document_page"),
    path("ressources/<int:resource_id>/telecharger/", documents.download, name="document_download"),
    path("enseignant/", teacher.dashboard, name="teacher_dashboard"),
    path("enseignant/etudiant/<int:student_id>/", teacher.student_detail, name="teacher_student"),
    path("enseignant/questions/", teacher.question_bank, name="teacher_question_bank"),
    path("enseignant/questions/nouvelle/", teacher.question_create, name="teacher_question_create"),
    path("enseignant/modules/", teacher.module_list, name="teacher_modules"),
    path("enseignant/modules/nouveau/", teacher.module_create, name="teacher_module_create"),
    path("enseignant/modules/<int:module_id>/", teacher.module_detail, name="teacher_module_detail"),
    path("enseignant/modules/<int:module_id>/supprimer/", teacher.module_delete, name="teacher_module_delete"),
    path(
        "enseignant/modules/<int:module_id>/question/<int:question_id>/supprimer/",
        teacher.module_question_delete,
        name="teacher_module_question_delete",
    ),
    path("enseignant/series/", teacher.series_list, name="teacher_series_list"),
    path("enseignant/series/<int:exam_number>/", teacher.series_detail, name="teacher_series_detail"),
    path("enseignant/question/<int:question_id>/modifier/", teacher.question_edit, name="teacher_question_edit"),
    path(
        "enseignant/question/<int:question_id>/controle/",
        teacher.question_toggle_checked,
        name="teacher_question_toggle_checked",
    ),
    path("enseignant/question/<int:question_id>/supprimer/", teacher.question_delete, name="teacher_question_delete"),
    path("enseignant/catalogue/telecharger/", teacher.catalogue_download, name="catalogue_download"),
    path("", views.dashboard, name="dashboard"),
    path("catalogue/", views.dashboard, {"template_name": "quiz/catalogue.html"}, name="catalogue"),
    path("practice/", views.practice, name="practice"),
    path("answer/<int:question_id>/", views.answer, name="answer"),
    path("feedback/<int:question_id>/", views.feedback, name="feedback"),
    path("reset/", views.reset_progress, name="reset_progress"),
    path("upload/", views.upload_exam, name="upload"),
    path("ressources/", views.resources, name="resources"),
]
