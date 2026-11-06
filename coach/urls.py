from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("signup/", views.signup, name="signup"),
    path("login/", auth_views.LoginView.as_view(redirect_authenticated_user=True), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("practice/", views.setup, name="setup"),
    path("practice/interview/", views.interview, name="interview"),
    path("practice/submit/", views.submit, name="submit"),
    path("sessions/", views.history, name="history"),
    path("sessions/<int:pk>/", views.result, name="result"),
    path("sessions/<int:pk>/snapshot.jpg", views.snapshot, name="snapshot"),
    path("sessions/<int:pk>/delete/", views.delete_session, name="delete_session"),
    path("account/", views.account, name="account"),
    path("contact/", views.contact, name="contact"),
]
