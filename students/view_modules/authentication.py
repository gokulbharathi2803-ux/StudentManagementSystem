from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.views import PasswordChangeView
from django.core.exceptions import PermissionDenied
from django.urls import reverse_lazy
from django.shortcuts import redirect, render
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_POST


@method_decorator(login_required, name="dispatch")
class StudentPasswordChangeView(PasswordChangeView):
    form_class = PasswordChangeForm
    template_name = "registration/password_change_form.html"
    success_url = reverse_lazy("student_dashboard")

    def dispatch(self, request, *args, **kwargs):
        if not request.user.groups.filter(name__iexact="Student").exists():
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

def role_login(request):
    if request.user.is_authenticated:
        if request.user.is_superuser:
            return redirect("admin_dashboard")

        if request.user.groups.filter(name__iexact="Teacher").exists():
            return redirect("teacher_dashboard")

        if request.user.groups.filter(name__iexact="Student").exists():
            return redirect("student_dashboard")

        if request.user.groups.filter(name__iexact="Admin").exists():
            return redirect("admin_dashboard")

        return redirect("dashboard")

    error = ""

    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        selected_role = request.POST.get("role", "").strip().lower()

        user = authenticate(
            request,
            username=username,
            password=password,
        )

        if user is not None:
            if selected_role in {"admin", "staff"}:
                is_admin = (
                    user.is_superuser
                    or user.groups.filter(name__iexact="Admin").exists()
                )
                is_teacher = user.groups.filter(
                    name__iexact="Teacher"
                ).exists()
                allowed = is_admin or (selected_role == "staff" and is_teacher)
                destination = (
                    "admin_dashboard" if is_admin else "teacher_dashboard"
                )

            elif selected_role == "teacher":
                allowed = user.groups.filter(
                    name__iexact="Teacher"
                ).exists()
                destination = "teacher_dashboard"

            elif selected_role == "student":
                allowed = user.groups.filter(
                    name__iexact="Student"
                ).exists()
                destination = "student_dashboard"

            else:
                allowed = False
                destination = "dashboard"

            if allowed:
                login(request, user)
                return redirect(destination)

        error = "Invalid username, password, or selected role."

    return render(
        request,
        "registration/login.html",
        {"error": error},
    )


@login_required
@require_POST
def role_logout(request):
    logout(request)
    return redirect("login")
