"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.urls import path, include

from students.view_modules.admin_views import (
    download_student_teacher_credentials,
    student_teacher_credentials,
)

urlpatterns = [
    path(
        "admin/studentms-credentials/",
        student_teacher_credentials,
        name="student_teacher_credentials",
    ),
    path(
        "admin/studentms-credentials/download.csv",
        download_student_teacher_credentials,
        name="download_student_teacher_credentials",
    ),
    path("admin/", admin.site.urls),
    path("", include("students.urls")),
]