from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("students", "0003_student_student_id"),
    ]

    operations = [
        migrations.AddField(
            model_name="student",
            name="must_change_password",
            field=models.BooleanField(default=False),
        ),
    ]
