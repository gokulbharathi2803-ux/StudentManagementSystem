from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.forms import UserCreationForm

from students.models import (
    Course,
    Department,
    Mark,
    Section,
    Semester,
    Student,
    Teacher,
)


class RoleLoginForm(AuthenticationForm):
    ROLE_CHOICES = [
        ("staff", "Staff"),
        ("teacher", "Teacher"),
        ("student", "Student"),
    ]

    role = forms.ChoiceField(
        choices=ROLE_CHOICES,
        widget=forms.RadioSelect,
        required=True,
        initial="staff",
    )

    def clean(self):
        cleaned_data = super().clean()

        user = self.get_user()
        selected_role = cleaned_data.get("role")

        if user and selected_role:
            is_admin = user.is_superuser or user.groups.filter(
                name__iexact="Admin"
            ).exists()

            is_teacher = user.groups.filter(
                name__iexact="Teacher"
            ).exists()

            is_student = user.groups.filter(
                name__iexact="Student"
            ).exists()

            if selected_role == "staff" and not (
                is_admin or is_teacher
            ):
                raise forms.ValidationError(
                    "This account is not registered as Staff."
                )

            if selected_role == "teacher" and not is_teacher:
                raise forms.ValidationError(
                    "This account is not registered as a Teacher."
                )

            if selected_role == "student" and not is_student:
                raise forms.ValidationError(
                    "This account is not registered as a Student."
                )

        return cleaned_data


class StudentForm(forms.ModelForm):
    class Meta:
        model = Student
        fields = (
            "student_id",
            "name",
            "email",
            "phone",
            "department",
            "course",
            "semester",
            "section",
        )
        widgets = {
            "student_id": forms.TextInput(attrs={"class": "form-control"}),
            "semester": forms.Select(attrs={"class": "form-control"}),
            "section": forms.Select(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["student_id"].required = True

    def clean_student_id(self):
        student_id = self.cleaned_data["student_id"].strip()
        matches = Student.objects.filter(student_id__iexact=student_id)
        if self.instance.pk:
            matches = matches.exclude(pk=self.instance.pk)
        if matches.exists():
            raise forms.ValidationError(
                "A student with this Student ID already exists."
            )
        return student_id

    def clean(self):
        cleaned_data = super().clean()
        semester = cleaned_data.get("semester")
        section = cleaned_data.get("section")
        if section and semester and section.semester_id != semester.pk:
            self.add_error("section", "Choose a section from the selected semester.")
        return cleaned_data


class DepartmentForm(forms.ModelForm):
    class Meta:
        model = Department
        fields = ("name", "description")

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        matches = Department.objects.filter(name__iexact=name)
        if self.instance.pk:
            matches = matches.exclude(pk=self.instance.pk)
        if matches.exists():
            raise forms.ValidationError("A department with this name already exists.")
        return name


class CourseForm(forms.ModelForm):
    class Meta:
        model = Course
        fields = ("name", "department", "duration")

    def clean(self):
        cleaned_data = super().clean()
        name = cleaned_data.get("name", "").strip()
        department = cleaned_data.get("department")
        if name and department:
            matches = Course.objects.filter(
                name__iexact=name,
                department=department,
            )
            if self.instance.pk:
                matches = matches.exclude(pk=self.instance.pk)
            if matches.exists():
                self.add_error(
                    "name",
                    "This department already has a course with this name.",
                )
        return cleaned_data


class SemesterForm(forms.ModelForm):
    class Meta:
        model = Semester
        fields = ("name", "number", "description")


class SectionForm(forms.ModelForm):
    class Meta:
        model = Section
        fields = ("name", "semester", "description")


class MarkForm(forms.ModelForm):
    component_maxima = {
        "internal_marks": 20,
        "assignment_marks": 20,
        "practical_marks": 20,
        "exam_marks": 70,
    }

    internal_marks = forms.IntegerField(
        min_value=0,
        max_value=20,
        widget=forms.NumberInput(attrs={"min": 0, "max": 20}),
    )
    assignment_marks = forms.IntegerField(
        min_value=0,
        max_value=20,
        widget=forms.NumberInput(attrs={"min": 0, "max": 20}),
    )
    practical_marks = forms.IntegerField(
        min_value=0,
        max_value=20,
        widget=forms.NumberInput(attrs={"min": 0, "max": 20}),
    )
    exam_marks = forms.IntegerField(
        min_value=0,
        max_value=70,
        widget=forms.NumberInput(attrs={"min": 0, "max": 70}),
    )

    class Meta:
        model = Mark
        fields = (
            "student",
            "subject",
            "internal_marks",
            "assignment_marks",
            "practical_marks",
            "exam_marks",
        )

    def __init__(self, *args, students=None, **kwargs):
        super().__init__(*args, **kwargs)
        if students is not None:
            self.fields["student"].queryset = students

    def clean(self):
        cleaned_data = super().clean()
        score_fields = tuple(self.component_maxima)
        if all(cleaned_data.get(field) is not None for field in score_fields):
            total = sum(cleaned_data[field] for field in score_fields)
            if total > 100:
                self.add_error(
                    "exam_marks",
                    "The combined assessment marks cannot exceed 100.",
                )
        return cleaned_data


class UserCreateForm(UserCreationForm):
    ROLE_CHOICES = (
        ("Admin", "Admin"),
        ("Teacher", "Teacher"),
        ("Student", "Student"),
    )

    email = forms.EmailField()
    role = forms.ChoiceField(choices=ROLE_CHOICES)
    student = forms.ModelChoiceField(
        queryset=Student.objects.none(),
        required=False,
        label="Link student record",
    )
    department = forms.ModelChoiceField(
        queryset=Department.objects.all(),
        required=False,
    )
    courses = forms.ModelMultipleChoiceField(
        queryset=Course.objects.all(),
        required=False,
    )
    name = forms.CharField(max_length=100, required=False)
    phone = forms.CharField(max_length=15, required=False)

    class Meta(UserCreationForm.Meta):
        model = get_user_model()
        fields = ("username", "email", "password1", "password2")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["student"].queryset = Student.objects.filter(user__isnull=True)
        self.fields["username"].help_text = (
            "Used for Admin accounts only. Student and Teacher usernames are "
            "generated from their profile identifiers."
        )
        self.fields["password1"].help_text = (
            "Used for Admin accounts only. Student and Teacher initial "
            "passwords follow their documented profile-based rules."
        )

    def clean_email(self):
        email = self.cleaned_data["email"].strip()
        user_model = get_user_model()
        if user_model.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def clean(self):
        cleaned_data = super().clean()
        role = cleaned_data.get("role")
        email = cleaned_data.get("email")
        student = cleaned_data.get("student")

        if role == "Student":
            if student is None:
                self.add_error("student", "Select a student record to link.")
            elif email and email.casefold() != student.email.casefold():
                self.add_error("email", "Student account email must match the student record.")

        if role == "Teacher":
            name = cleaned_data.get("name", "").strip()
            if not name:
                self.add_error("name", "Enter the teacher's name.")
            if email and Teacher.objects.filter(email__iexact=email).exists():
                self.add_error("email", "A teacher profile already uses this email.")

        return cleaned_data
