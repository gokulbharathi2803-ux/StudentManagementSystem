def role_context(request):
    user = request.user

    if not user.is_authenticated:
        return {
            "is_admin": False,
            "is_teacher": False,
            "is_student": False,
            "can_delete_students": False,
        }

    roles = {
        name.lower()
        for name in user.groups.values_list("name", flat=True)
    }
    is_admin = user.is_superuser or "admin" in roles
    is_teacher = not is_admin and "teacher" in roles
    is_student = not is_admin and not is_teacher and "student" in roles

    return {
        "is_admin": is_admin,
        "is_teacher": is_teacher,
        "is_student": is_student,
        "can_delete_students": is_admin,
    }
