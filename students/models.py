
from django.conf import settings
from django.db import models


class Semester(models.Model):
    name = models.CharField(max_length=50, unique=True)
    number = models.PositiveIntegerField(unique=True)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["number"]

    def __str__(self):
        return self.name


class Section(models.Model):
    name = models.CharField(max_length=10)
    semester = models.ForeignKey(
        Semester,
        on_delete=models.CASCADE,
        related_name="sections",
    )
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["semester__number", "name"]
        unique_together = ("name", "semester")

    def __str__(self):
        return f"{self.semester.name} - Section {self.name}"


class Department(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Course(models.Model):
    name = models.CharField(max_length=100)
    department = models.ForeignKey(
        Department,
        on_delete=models.CASCADE,
        related_name="courses",
    )
    duration = models.CharField(max_length=50, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Student(models.Model):
    student_id = models.CharField(
        max_length=32,
        unique=True,
        null=True,
        blank=True,
        verbose_name="Student ID",
    )
    must_change_password = models.BooleanField(default=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="student_profile",
    )
    name = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=15, blank=True)
    department = models.CharField(max_length=100)
    course = models.CharField(max_length=100)
    semester = models.ForeignKey(
        Semester,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="students",
    )
    section = models.ForeignKey(
        Section,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="students",
    )

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Teacher(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="teacher_profile",
    )
    name = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=15, blank=True)
    department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="teachers",
    )
    courses = models.ManyToManyField(
        Course,
        blank=True,
        related_name="teachers",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class InitialLoginCredential(models.Model):
    ROLE_CHOICES = (
        ("Student", "Student"),
        ("Teacher", "Teacher"),
    )

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="initial_login_credential",
    )
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    encrypted_password = models.TextField()
    is_valid = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        permissions = [
            (
                "manage_login_credentials",
                "Can generate and download student/teacher login credentials",
            ),
        ]

    def __str__(self):
        return f"{self.role} initial credential for {self.user.username}"


class Attendance(models.Model):
    STATUS_CHOICES = [
        ("Present", "Present"),
        ("Absent", "Absent"),
    ]

    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="attendance",
    )
    date = models.DateField()
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
    )

    class Meta:
        unique_together = ("student", "date")
        ordering = ["-date"]

    def __str__(self):
        return f"{self.student.name} - {self.date} - {self.status}"


class Mark(models.Model):
    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="marks",
    )
    subject = models.CharField(max_length=100)
    internal_marks = models.PositiveIntegerField(default=0)
    assignment_marks = models.PositiveIntegerField(default=0)
    practical_marks = models.PositiveIntegerField(default=0)
    exam_marks = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["student__name", "subject"]

    @property
    def total_marks(self):
        return (
            self.internal_marks
            + self.assignment_marks
            + self.practical_marks
            + self.exam_marks
        )

    @property
    def percentage(self):
        return round(self.total_marks, 2)

    @property
    def grade(self):
        percentage = self.percentage

        if percentage >= 90:
            return "A+"
        elif percentage >= 80:
            return "A"
        elif percentage >= 70:
            return "B"
        elif percentage >= 60:
            return "C"
        elif percentage >= 50:
            return "D"
        return "F"

    @property
    def result(self):
        return "Pass" if self.percentage >= 40 else "Fail"

    def __str__(self):
        return f"{self.student.name} - {self.subject}"
