from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from .questions import LEVEL_CHOICES, ROLE_CHOICES


class SignUpForm(UserCreationForm):
    email = forms.EmailField(required=True)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email")

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email


class PracticeSetupForm(forms.Form):
    role = forms.ChoiceField(choices=ROLE_CHOICES, label="Target role")
    level = forms.ChoiceField(choices=LEVEL_CHOICES, label="Experience")
    skills = forms.CharField(
        required=False,
        max_length=300,
        label="Key skills",
        help_text="Comma-separated, e.g. Python, SQL, React. Used to personalise a question.",
        widget=forms.TextInput(attrs={"placeholder": "Python, SQL, Figma"}),
    )
    question_count = forms.TypedChoiceField(
        choices=[(3, "3 questions (~5 min)"), (5, "5 questions (~10 min)")],
        coerce=int,
        initial=5,
        label="Session length",
    )


class ContactForm(forms.Form):
    name = forms.CharField(max_length=100)
    email = forms.EmailField()
    message = forms.CharField(max_length=2000, widget=forms.Textarea(attrs={"rows": 5}))
