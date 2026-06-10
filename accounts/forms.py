from django import forms
from django.contrib.auth.models import User, Group
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db.models import Q

class UserCreateForm(forms.ModelForm):
    password1 = forms.CharField(label="Contraseña", widget=forms.PasswordInput, required=True)
    password2 = forms.CharField(label="Confirmar contraseña", widget=forms.PasswordInput, required=True)
    groups = forms.ModelMultipleChoiceField(
        label="Roles (grupos)",
        queryset=Group.objects.all().order_by("name"),
        required=False,
        widget=forms.CheckboxSelectMultiple()
    )

    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "email", "is_active", "is_staff"]
        widgets = {
            "username": forms.TextInput(attrs={"class": "form-control"}),
            "first_name": forms.TextInput(attrs={"class": "form-control"}),
            "last_name": forms.TextInput(attrs={"class": "form-control"}),
            "email": forms.EmailInput(attrs={"class": "form-control"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "is_staff": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get("password1")
        p2 = cleaned.get("password2")
        if p1 != p2:
            raise ValidationError("Las contraseñas no coinciden.")
        validate_password(p1)
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
            self.save_m2m()
        return user


class UserUpdateForm(forms.ModelForm):
    password1 = forms.CharField(label="Nueva contraseña (opcional)", widget=forms.PasswordInput, required=False)
    password2 = forms.CharField(label="Confirmar nueva contraseña", widget=forms.PasswordInput, required=False)
    groups = forms.ModelMultipleChoiceField(
        label="Roles (grupos)",
        queryset=Group.objects.all().order_by("name"),
        required=False,
        widget=forms.CheckboxSelectMultiple()
    )

    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "email", "is_active", "is_staff"]
        widgets = {
            "username": forms.TextInput(attrs={"class": "form-control"}),
            "first_name": forms.TextInput(attrs={"class": "form-control"}),
            "last_name": forms.TextInput(attrs={"class": "form-control"}),
            "email": forms.EmailInput(attrs={"class": "form-control"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "is_staff": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get("password1")
        p2 = cleaned.get("password2")

        if p1 or p2:
            if p1 != p2:
                raise ValidationError("Las contraseñas no coinciden.")
            validate_password(p1)

        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        p1 = self.cleaned_data.get("password1")
        if p1:
            user.set_password(p1)
        if commit:
            user.save()
            self.save_m2m()
        return user


class RoleForm(forms.ModelForm):
    permissions = forms.ModelMultipleChoiceField(
        label="Permisos CRUD",
        queryset=None,
        required=False,
        widget=forms.CheckboxSelectMultiple(),
    )

    class Meta:
        model = Group
        fields = ["name", "permissions"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ej. Ventas"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from django.contrib.auth.models import Permission
        from django.contrib.contenttypes.models import ContentType

        apps_visibles = ["auth", "catalogos", "inventarios", "cartera", "cotizaciones", "accounts"]
        acciones_crud = ["view", "add", "change", "delete"]

        accion_filter = Q()
        for accion in acciones_crud:
            accion_filter |= Q(codename__startswith=f"{accion}_")

        self.fields["permissions"].queryset = (
            Permission.objects
            .select_related("content_type")
            .filter(content_type__app_label__in=apps_visibles)
            .filter(accion_filter)
            .order_by("content_type__app_label", "content_type__model", "codename")
        )

        accion_labels = {
            "view": "Ver",
            "add": "Agregar",
            "change": "Modificar",
            "delete": "Eliminar",
        }

        def _perm_label(perm):
            accion = perm.codename.split("_", 1)[0]
            accion_txt = accion_labels.get(accion, accion.capitalize())
            modelo = perm.content_type.model.replace("_", " ").title()
            modulo = perm.content_type.app_label.title()
            return f"{modulo} / {modelo} / {accion_txt}"

        self.fields["permissions"].label_from_instance = _perm_label

        self.fields["permissions"].help_text = (
            "Selecciona qué puede hacer este rol. "
            "Ver = consultar, Agregar = crear, Modificar = editar/procesar, Eliminar = borrar/cancelar según el flujo."
        )
