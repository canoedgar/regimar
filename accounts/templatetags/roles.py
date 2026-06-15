from django import template

register = template.Library()

@register.filter
def has_group(user, group_name: str) -> bool:
    if not user or not user.is_authenticated:
        return False
    return user.groups.filter(name=group_name).exists()

@register.simple_tag
def in_any_group(user, *group_names) -> bool:
    if not user or not user.is_authenticated:
        return False
    return user.groups.filter(name__in=group_names).exists()


@register.simple_tag
def has_any_perm(user, *permisos) -> bool:
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return any(user.has_perm(permiso) for permiso in permisos if permiso)

@register.simple_tag
def has_all_perm(user, *permisos) -> bool:
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    permisos = tuple(permiso for permiso in permisos if permiso)
    return bool(permisos) and user.has_perms(permisos)
