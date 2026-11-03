from django.db import migrations


def create_default_course_group(apps, schema_editor):
    CourseGroup = apps.get_model("quiz", "CourseGroup")
    CourseGroup.objects.get_or_create(name="HEPL")


class Migration(migrations.Migration):
    dependencies = [
        ("quiz", "0005_module_alter_question_unique_together_and_more"),
    ]

    operations = [
        migrations.RunPython(create_default_course_group, migrations.RunPython.noop),
    ]
