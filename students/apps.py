from django.apps import AppConfig


class StudentsConfig(AppConfig):
    name = 'students'

    def ready(self):
        from students import signals  # noqa: F401
