from django.contrib import messages
from django.contrib.auth.models import Group, User
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.decorators import administrador_requerido
from .forms import RoleForm, UserCreateForm, UserUpdateForm


@administrador_requerido
def users_list(request):
    q = (request.GET.get("q") or "").strip()
    users = User.objects.prefetch_related("groups").all().order_by("username")
    if q:
        users = users.filter(
            Q(username__icontains=q)
            | Q(email__icontains=q)
            | Q(first_name__icontains=q)
            | Q(last_name__icontains=q)
        )

    return render(request, "accounts/users_list.html", {"users": users, "q": q})


@administrador_requerido
def users_create(request):
    if request.method == "POST":
        form = UserCreateForm(request.POST)
        if form.is_valid():
            user = form.save()
            user.groups.set(form.cleaned_data["groups"])
            messages.success(request, "Usuario creado correctamente.")
            return redirect("users_list")
    else:
        form = UserCreateForm(initial={"is_active": True, "is_staff": False})
    return render(request, "accounts/users_form.html", {"form": form, "modo": "create"})


@administrador_requerido
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


@administrador_requerido
@require_POST
def users_toggle_active(request, pk):
    user_obj = get_object_or_404(User, pk=pk)

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


@administrador_requerido
def roles_list(request):
    q = (request.GET.get("q") or "").strip()
    roles = (
        Group.objects
        .annotate(total_usuarios=Count("user", distinct=True), total_permisos=Count("permissions", distinct=True))
        .order_by("name")
    )
    if q:
        roles = roles.filter(name__icontains=q)

    return render(request, "accounts/roles_list.html", {"roles": roles, "q": q})


@administrador_requerido
def roles_create(request):
    if request.method == "POST":
        form = RoleForm(request.POST)
        if form.is_valid():
            role = form.save()
            messages.success(request, f"Rol '{role.name}' creado correctamente.")
            return redirect("roles_list")
    else:
        form = RoleForm()

    return render(request, "accounts/roles_form.html", {"form": form, "modo": "create"})


@administrador_requerido
def roles_update(request, pk):
    role = get_object_or_404(Group, pk=pk)
    if request.method == "POST":
        form = RoleForm(request.POST, instance=role)
        if form.is_valid():
            role = form.save()
            messages.success(request, f"Rol '{role.name}' actualizado correctamente.")
            return redirect("roles_list")
    else:
        form = RoleForm(instance=role)

    return render(request, "accounts/roles_form.html", {"form": form, "modo": "update", "role": role})


@administrador_requerido
@require_POST
def roles_delete(request, pk):
    role = get_object_or_404(Group, pk=pk)
    if role.user_set.exists():
        messages.error(request, "No puedes eliminar un rol que tiene usuarios asignados. Retira primero el rol de los usuarios.")
        return redirect("roles_list")

    nombre = role.name
    role.delete()
    messages.success(request, f"Rol '{nombre}' eliminado correctamente.")
    return redirect("roles_list")
