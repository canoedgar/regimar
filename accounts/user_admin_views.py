from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404, redirect, render

from .forms import UserCreateForm, UserUpdateForm

def superuser_required(view):
    return user_passes_test(lambda u: u.is_authenticated and u.is_superuser)(view)

@superuser_required
def users_list(request):
    q = (request.GET.get("q") or "").strip()
    users = User.objects.all().order_by("username")
    if q:
        users = users.filter(username__icontains=q) | users.filter(email__icontains=q) | users.filter(first_name__icontains=q) | users.filter(last_name__icontains=q)

    return render(request, "accounts/users_list.html", {"users": users, "q": q})

@superuser_required
def users_create(request):
    if request.method == "POST":
        form = UserCreateForm(request.POST)
        if form.is_valid():
            user = form.save()
            # asignar grupos (roles)
            user.groups.set(form.cleaned_data["groups"])
            messages.success(request, "Usuario creado correctamente.")
            return redirect("users_list")
    else:
        form = UserCreateForm(initial={"is_active": True, "is_staff": False})
    return render(request, "accounts/users_form.html", {"form": form, "modo": "create"})

@superuser_required
def users_update(request, pk):
    user_obj = get_object_or_404(User, pk=pk)

    if request.method == "POST":
        form = UserUpdateForm(request.POST, instance=user_obj)
        if form.is_valid():
            user = form.save()
            user.groups.set(form.cleaned_data["groups"])
            messages.success(request, "Usuario actualizado correctamente.")
            return redirect("users_list")
    else:
        form = UserUpdateForm(instance=user_obj, initial={"groups": user_obj.groups.all()})

    return render(request, "accounts/users_form.html", {"form": form, "modo": "update", "user_obj": user_obj})

@superuser_required
def users_toggle_active(request, pk):
    user_obj = get_object_or_404(User, pk=pk)

    # Evita que el superuser se deshabilite a sí mismo por accidente
    if user_obj == request.user:
        messages.error(request, "No puedes inhabilitar tu propio usuario.")
        return redirect("users_list")

    user_obj.is_active = not user_obj.is_active
    user_obj.save(update_fields=["is_active"])

    if user_obj.is_active:
        messages.success(request, f"Usuario '{user_obj.username}' habilitado.")
    else:
        messages.warning(request, f"Usuario '{user_obj.username}' inhabilitado.")

    return redirect("users_list")
