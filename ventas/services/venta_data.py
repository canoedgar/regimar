from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass
class VentaRequestContext:
    """
    Contexto mínimo que requiere el dominio de ventas.

    Evita que los servicios lean directamente request.POST, request.user o
    request.build_absolute_uri. La vista sigue siendo la responsable de adaptar
    el request web a datos simples de operación.
    """
    usuario: Any = None
    credito_request: Any = None
    confirmar_envio_autorizacion_precio: bool = False
    absolute_uri_builder: Optional[Callable[[str], str]] = None

    @classmethod
    def from_request(cls, request):
        if request is None:
            return cls()

        usuario = getattr(request, "user", None)
        usuario_autenticado = usuario if getattr(usuario, "is_authenticated", False) else None
        post_data = getattr(request, "POST", None)
        confirmar_precio = False
        if post_data is not None:
            confirmar_precio = post_data.get("confirmar_envio_autorizacion_precio") == "1"

        return cls(
            usuario=usuario_autenticado,
            credito_request=request,
            confirmar_envio_autorizacion_precio=confirmar_precio,
            absolute_uri_builder=getattr(request, "build_absolute_uri", None),
        )

    def build_absolute_uri(self, path: str) -> str:
        if self.absolute_uri_builder:
            return self.absolute_uri_builder(path)
        return path

    def username(self) -> str:
        if self.usuario and getattr(self.usuario, "is_authenticated", False):
            return self.usuario.get_username()
        return "Sistema"


@dataclass
class VentaOperacionData:
    """
    Datos de negocio necesarios para registrar o validar una venta.

    `salida` es la entidad de salida ya preparada por la capa de vista/formulario
    pero aún no persistida cuando se trata de una venta nueva.
    """
    salida: Any
    cliente: Any = None
    fecha: Any = None
    contexto: VentaRequestContext = field(default_factory=VentaRequestContext)
    venta_existente: Any = None
    total_venta_override: Any = None
    validar_credito: bool = True

    @classmethod
    def from_form(cls, form, *, request_context=None, venta_existente=None, total_venta_override=None, validar_credito=True):
        salida = form.save(commit=False)
        cleaned_data = getattr(form, "cleaned_data", {}) or {}
        return cls(
            salida=salida,
            cliente=cleaned_data.get("cliente_ref"),
            fecha=cleaned_data.get("fecha"),
            contexto=request_context or VentaRequestContext(),
            venta_existente=venta_existente,
            total_venta_override=total_venta_override,
            validar_credito=validar_credito,
        )
