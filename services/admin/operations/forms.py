"""Custom Django admin forms for operations models."""

from typing import Any

import bcrypt
from django import forms

from operations.models import Tenant, User


class TenantAdminForm(forms.ModelForm):
    """Form that makes the JSONB columns optional while preserving their
    defaults, so tenants created in the admin panel satisfy the NOT NULL
    constraints of the FastAPI-managed schema.
    """

    class Meta:
        model = Tenant
        fields = "__all__"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        for name in (
            "settings",
            "onboarding_progress",
            "nations_served",
            "quote_defaults",
            "branding",
        ):
            self.fields[name].required = False

    def clean(self) -> dict[str, Any]:
        cleaned_data = super().clean()
        for name in (
            "settings",
            "onboarding_progress",
            "nations_served",
            "quote_defaults",
            "branding",
        ):
            if cleaned_data.get(name) is None:
                cleaned_data[name] = Tenant._meta.get_field(name).get_default()
        return cleaned_data


class UserAdminForm(forms.ModelForm):
    """Form that hashes the plain-text password using the same bcrypt
    scheme as the FastAPI auth service, so users created in the admin panel
    can log in to the back-office UI.
    """

    password = forms.CharField(
        widget=forms.PasswordInput,
        required=False,
        help_text="Leave blank to keep the existing password unchanged.",
    )

    class Meta:
        model = User
        fields = "__all__"

    def save(self, commit: bool = True) -> User:
        user = super().save(commit=False)
        password = self.cleaned_data.get("password")
        if password:
            user.password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode(
                "utf-8"
            )
        if commit:
            user.save()
        return user  # type: ignore[no-any-return]
