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
