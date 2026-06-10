from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


ADMIN_GROUP_NAME = "Administrador"


def _es_administrador_sistema(user):
    return (
        user.is_authenticated
        and (
            user.is_superuser
            or user.groups.filter(name=ADMIN_GROUP_NAME).exists()
        )
    )


def grupos_requeridos(*nombres_grupo):
    """
    Restringe una vista a usuarios autenticados que pertenezcan a uno de los
    grupos indicados. Los superusuarios siempre tienen acceso.

    Se conserva por compatibilidad con vistas que siguen trabajando por módulo.
    Para la seguridad granular usar `permiso_requerido`.
    """
    nombres_grupo = tuple(nombres_grupo)

    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def _wrapped_view(request, *args, **kwargs):
            user = request.user
            if user.is_superuser:
                return view_func(request, *args, **kwargs)
            if nombres_grupo and user.groups.filter(name__in=nombres_grupo).exists():
                return view_func(request, *args, **kwargs)
            raise PermissionDenied

        return _wrapped_view

    return decorator


def administrador_requerido(view_func):
    """Restringe una vista a superusuarios o usuarios del grupo Administrador."""
    return grupos_requeridos(ADMIN_GROUP_NAME)(view_func)


def permiso_requerido(*permisos, require_all=False):
    """
    Restringe una vista por permisos específicos de Django.

    Ejemplos:
      @permiso_requerido("catalogos.view_cliente")
      @permiso_requerido("catalogos.add_cliente")
      @permiso_requerido("inventarios.change_salidainventario")

    Los superusuarios y el grupo Administrador conservan acceso total para no
    bloquear la administración operativa. El resto de usuarios depende de los
    permisos asignados a su rol desde Configuración > Roles y permisos.
    """
    permisos = tuple(p for p in permisos if p)

    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def _wrapped_view(request, *args, **kwargs):
            user = request.user

            if _es_administrador_sistema(user):
                return view_func(request, *args, **kwargs)

            if not permisos:
                raise PermissionDenied

            tiene_permiso = user.has_perms(permisos) if require_all else any(user.has_perm(p) for p in permisos)
            if tiene_permiso:
                return view_func(request, *args, **kwargs)

            raise PermissionDenied

        return _wrapped_view

    return decorator
