from functools import wraps

from django.core.exceptions import PermissionDenied
from django.db.models import QuerySet
from django.shortcuts import get_object_or_404

from students.models import Course, Student, Teacher


def user_has_role(user, role):
    """Check whether a user belongs to a particular role."""
    if not user.is_authenticated:
        return False

    if user.is_superuser:
        return role.casefold() == "admin"

    return user.groups.filter(name__iexact=role).exists()


def is_admin(user):
    return user.is_authenticated and (
        user.is_superuser or user_has_role(user, "Admin")
    )


def is_teacher(user):
    return user.is_authenticated and user_has_role(user, "Teacher")


def get_student_profile(user):
    student = Student.objects.filter(user=user).first()
    if student is not None:
        return student
    return Student.objects.filter(email__iexact=user.email).first()


def get_teacher_profile(user):
    return Teacher.objects.filter(user=user).first()


def students_for_teacher(user) -> QuerySet[Student]:
    teacher = get_teacher_profile(user)
    if teacher is None:
        return Student.objects.none()

    course_names = teacher.courses.values_list("name", flat=True)
    return Student.objects.filter(course__in=course_names)


def get_authorized_student(user, student_id):
    if is_admin(user):
        students = Student.objects.all()
    elif is_teacher(user):
        students = students_for_teacher(user)
    else:
        students = Student.objects.none()
    return get_object_or_404(students, pk=student_id)


def role_required(*roles):
    """Restrict a view to users with one of the specified roles."""

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                from django.contrib.auth.views import redirect_to_login
                return redirect_to_login(request.get_full_path())

            if not any(
                user_has_role(request.user, role)
                or (role.casefold() == "admin" and request.user.is_superuser)
                for role in roles
            ):
                raise PermissionDenied

            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator