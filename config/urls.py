from django.contrib import admin
from django.urls import include, path

# Media files (posture snapshots) are deliberately not served publicly;
# see coach.views.snapshot, which checks ownership first.
urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("coach.urls")),
]
