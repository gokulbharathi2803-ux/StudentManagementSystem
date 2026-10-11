from django.shortcuts import redirect

from students.models import Student


class StudentInitialPasswordMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        user = request.user
        if not user.is_authenticated or user.is_staff or user.is_superuser:
            return None
        if not user.groups.filter(name__iexact="Student").exists():
            return None

        student = (
            Student.objects.filter(user=user)
            .only("must_change_password")
            .first()
        )
        if (
            student
            and student.must_change_password
            and request.resolver_match.url_name
            not in {"student_password_change", "logout"}
        ):
            return redirect("student_password_change")
        return None
