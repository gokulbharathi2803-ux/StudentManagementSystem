from django.db import migrations, models


def backfill_sample_student_ids(apps, schema_editor):
    Student = apps.get_model("students", "Student")
    database = schema_editor.connection.alias

    for number in range(1, 101):
        email = f"student{number:03d}@example.com"
        student_id = f"STU{number:04d}"
        Student.objects.using(database).filter(email__iexact=email).update(
            student_id=student_id
        )


class Migration(migrations.Migration):
    dependencies = [
        ("students", "0002_alter_course_options_alter_department_options_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="student",
            name="student_id",
            field=models.CharField(
                blank=True,
                max_length=32,
                null=True,
                unique=True,
                verbose_name="Student ID",
            ),
        ),
        migrations.RunPython(
            backfill_sample_student_ids,
            migrations.RunPython.noop,
        ),
    ]
