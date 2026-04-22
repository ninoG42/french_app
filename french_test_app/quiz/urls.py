from django.urls import path

from . import views

app_name = "quiz"
urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("practice/", views.practice, name="practice"),
    path("answer/<int:question_id>/", views.answer, name="answer"),
    path("feedback/<int:question_id>/", views.feedback, name="feedback"),
    path("reset/", views.reset_progress, name="reset_progress"),
    path("upload/", views.upload_exam, name="upload"),
]
