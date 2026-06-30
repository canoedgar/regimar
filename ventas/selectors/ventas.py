from decimal import Decimal

from django.core.paginator import Paginator
from django.db.models import Count, Prefetch, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from inventarios.models import SalidaInventario, SalidaInventarioDetalle
from ventas.models import NotaVenta
from ventas.services.comisiones import MONEY_FIELD, total_importe_con_comision_expr
from ventas.services.impresion import importe_detalles_expr, importe_linea_expr

from catalogos.models import Almacen, Cliente, ClienteProductoPrecio, Producto
from inventarios.models import InventarioStock
from inventarios.utils import (
    decimal_or_default as _to_decimal,
    decimal_text as _decimal_text,
    get_almacen_default,
)


def _nombre_metrica(obj):
    if obj is None:
        return ""

    return (
        getattr(obj, "abreviatura", None)
        or getattr(obj, "nombre", None)
        or getattr(obj, "nombre_metrica", None)
        or str(obj)
    )


def _conversiones_producto(producto):
    default_name = _nombre_metrica(getattr(producto, "metrica", None)) or "kg"

    conversiones = [{
        "id": "default",
        "cantidad_origen": 1.0,
        "unidad_origen": default_name,
        "factor_conversion": 1.0,
        "equivalencia_texto": f"1 {default_name} = 1 {default_name}",
        "es_default": True,
    }]

    rel = None

    for attr in ("conversiones_metricas", "conversiones"):
        if hasattr(producto, attr):
            rel = getattr(producto, attr)
            break

    if rel is None:
        return conversiones

    try:
        rows = rel.all()
    except Exception:
        return conversiones

    for conv in rows:
        cantidad_origen = (
            _to_decimal(
                getattr(conv, "cantidad_origen", None),
                default=Decimal("1"),
            )
            or Decimal("1")
        )

        factor = (
            _to_decimal(
                getattr(conv, "factor_conversion", None),
                default=Decimal("0"),
            )
            or Decimal("0")
        )

        unidad_origen = (
            _nombre_metrica(getattr(conv, "unidad_origen", None))
            or _nombre_metrica(getattr(conv, "metrica", None))
            or default_name
        )

        conversiones.append({
            "id": str(getattr(conv, "id", "")) or f"conv-{len(conversiones)}",
            "cantidad_origen": float(cantidad_origen),
            "unidad_origen": unidad_origen,
            "factor_conversion": float(factor),
            "equivalencia_texto": (
                getattr(conv, "equivalencia_texto", None)
                or f"{_decimal_text(cantidad_origen)} "
                   f"{unidad_origen} = "
                   f"{_decimal_text(factor)} "
                   f"{default_name}"
            ),
            "es_default": False,
        })

    return conversiones


def _almacen_permite_venta_sin_stock(almacen):
    return bool(
        getattr(almacen, "es_virtual_sistema", False)
        or getattr(almacen, "tipo", "") == "VIRTUAL"
    )


def _producto_ui_base(producto):
    return {
        "id": str(producto.id),
        "nombre": producto.nombre,
        "stock": 0.0,
        "precio": float(getattr(producto, "precio", 0) or 0),
        "precio_minimo": float(getattr(producto, "precio_minimo", 0) or 0),
        "maneja_peso_variable": bool(getattr(producto, "maneja_peso_variable", False)),
        "costo_promedio": float(getattr(producto, "costo_promedio", 0) or 0),
        "ultimo_costo_compra": float(getattr(producto, "ultimo_costo_compra", 0) or 0),
        "codigo": getattr(producto, "codigo", "") or "",
        "clave_busqueda": getattr(producto, "clave_busqueda", "") or "",
        "metrica_default": _nombre_metrica(getattr(producto, "metrica", None)) or "kg",
        "conversiones": _conversiones_producto(producto),
        "almacenes": [],
    }


def _almacen_ui(almacen, cantidad):
    venta_sin_stock = _almacen_permite_venta_sin_stock(almacen)
    return {
        "id": str(almacen.id),
        "codigo": getattr(almacen, "codigo", "") or "",
        "nombre": getattr(almacen, "nombre", "") or "",
        "tipo": getattr(almacen, "tipo", "") or "",
        "es_virtual_sistema": bool(getattr(almacen, "es_virtual_sistema", False)),
        "permite_venta_sin_stock": venta_sin_stock,
        "stock": float(cantidad or 0),
        "label": (f"{getattr(almacen, 'codigo', '')} - {getattr(almacen, 'nombre', '')}").strip(" -"),
    }


def build_productos_ui():
    almacenes_activos = list(Almacen.objects.filter(es_activo=True).order_by("tipo", "nombre"))
    almacenes_virtuales = [a for a in almacenes_activos if _almacen_permite_venta_sin_stock(a)]

    productos_map = {
        str(producto.id): _producto_ui_base(producto)
        for producto in Producto.objects.all().order_by("nombre")
    }

    stocks = (
        InventarioStock.objects
        .filter(almacen__es_activo=True)
        .select_related("producto", "almacen")
        .order_by("producto__nombre", "almacen__tipo", "almacen__nombre")
    )

    almacenes_por_producto = {producto_id: set() for producto_id in productos_map.keys()}

    for stock in stocks:
        producto = stock.producto
        producto_id = str(producto.id)
        item = productos_map.setdefault(producto_id, _producto_ui_base(producto))

        cantidad = float(stock.cantidad or 0)
        item["stock"] += cantidad
        item["almacenes"].append(_almacen_ui(stock.almacen, cantidad))
        almacenes_por_producto.setdefault(producto_id, set()).add(str(stock.almacen_id))

    # Los almacenes virtuales deben permitir venta de cualquier producto aunque no exista
    # fila previa en InventarioStock. El backend generará entrada y salida automática.
    for producto_id, item in productos_map.items():
        ya_agregados = almacenes_por_producto.setdefault(producto_id, set())
        for almacen in almacenes_virtuales:
            if str(almacen.id) in ya_agregados:
                continue
            item["almacenes"].append(_almacen_ui(almacen, 0))
            ya_agregados.add(str(almacen.id))

    cliente_precios = ClienteProductoPrecio.objects.select_related("cliente", "producto")

    for precio_cliente in cliente_precios:
        producto_id = str(precio_cliente.producto_id)
        if producto_id not in productos_map:
            continue
        item = productos_map[producto_id]
        item.setdefault("precios_clientes", {})[str(precio_cliente.cliente_id)] = {
            "precio": float(precio_cliente.ultimo_precio or 0),
            "fecha": precio_cliente.fecha_ultimo_precio.isoformat() if precio_cliente.fecha_ultimo_precio else "",
            "dias_sin_compra": precio_cliente.dias_sin_compra,
            "vigente": precio_cliente.vigente,
        }

    productos_ui = list(productos_map.values())
    productos_ui.sort(key=lambda item: (item.get("nombre") or "").lower())

    return productos_ui

def get_contexto_salida_venta():
    almacenes_qs = Almacen.objects.filter(
        es_activo=True
    ).order_by(
        "tipo",
        "nombre",
    )

    almacen_default = get_almacen_default() or almacenes_qs.first()

    clientes = Cliente.objects.all().order_by("nombre_fiscal")

    return {
        "productos_ui": build_productos_ui(),
        "clientes": clientes,
        "almacenes_qs": almacenes_qs,
        "almacen_default": almacen_default,
    }

def _detalle_venta_filtrado_qs(request):
    qs = (
        SalidaInventarioDetalle.objects
        .select_related("producto", "almacen")
        .prefetch_related("asignaciones__almacen")
        .annotate(importe=importe_linea_expr())
        .order_by("id")
    )

    producto_id = (request.GET.get("producto") or "").strip()
    presentacion = (request.GET.get("presentacion") or "").strip()
    almacen_id = (request.GET.get("almacen") or "").strip()

    if producto_id.isdigit():
        qs = qs.filter(producto_id=int(producto_id))
    if presentacion:
        qs = qs.filter(presentacion_nombre__icontains=presentacion)
    if almacen_id.isdigit():
        qs = qs.filter(
            Q(almacen_id=int(almacen_id))
            | Q(asignaciones__almacen_id=int(almacen_id))
            | Q(salida__almacen_id=int(almacen_id))
        ).distinct()

    return qs


def _ventas_filtradas_qs(request):
    ventas = (
        NotaVenta.objects
        .select_related("salida", "salida__almacen", "cliente_ref")
        .order_by("-fecha", "-folio")
    )

    folio = (request.GET.get("folio") or "").strip()
    cliente = (request.GET.get("cliente") or "").strip()
    fecha_inicio = (request.GET.get("fecha_inicio") or "").strip()
    fecha_fin = (request.GET.get("fecha_fin") or "").strip()
    estado = (request.GET.get("estado") or "").strip()
    estado_pago = (request.GET.get("estado_pago") or "").strip()
    producto_id = (request.GET.get("producto") or "").strip()
    almacen_id = (request.GET.get("almacen") or "").strip()
    presentacion = (request.GET.get("presentacion") or "").strip()

    if not request.GET:
        hoy = timezone.localdate().isoformat()
        fecha_inicio = hoy
        fecha_fin = hoy

    if folio:
        ventas = ventas.filter(folio__icontains=folio)
    if cliente:
        ventas = ventas.filter(cliente__icontains=cliente)
    if fecha_inicio:
        ventas = ventas.filter(fecha__gte=fecha_inicio)
    if fecha_fin:
        ventas = ventas.filter(fecha__lte=fecha_fin)
    if estado in dict(NotaVenta.ESTADO_CHOICES):
        ventas = ventas.filter(estado=estado)
    if estado_pago in dict(NotaVenta.ESTADO_PAGO_CHOICES):
        ventas = ventas.filter(estado_pago=estado_pago)
    if producto_id.isdigit():
        ventas = ventas.filter(salida__detalles__producto_id=int(producto_id))
    if almacen_id.isdigit():
        ventas = ventas.filter(
            Q(salida__almacen_id=int(almacen_id))
            | Q(salida__detalles__almacen_id=int(almacen_id))
            | Q(salida__detalles__asignaciones__almacen_id=int(almacen_id))
        )
    if presentacion:
        ventas = ventas.filter(salida__detalles__presentacion_nombre__icontains=presentacion)

    filtros = request.GET.copy()
    if not request.GET:
        filtros["fecha_inicio"] = fecha_inicio
        filtros["fecha_fin"] = fecha_fin

    return ventas, filtros


def _marcar_almacen_display(page_obj):
    for venta in page_obj.object_list:
        venta.detalles_filtrados = getattr(getattr(venta, "salida", None), "detalles_filtrados", [])
        almacenes_por_id = {}
        if getattr(venta, "almacen_id", None) and getattr(venta, "almacen", None):
            almacenes_por_id[venta.almacen_id] = venta.almacen

        for detalle in getattr(venta, "detalles_filtrados", []):
            if getattr(detalle, "almacen_id", None) and getattr(detalle, "almacen", None):
                almacenes_por_id[detalle.almacen_id] = detalle.almacen
            for asignacion in getattr(detalle, "asignaciones", []).all():
                if getattr(asignacion, "almacen_id", None) and getattr(asignacion, "almacen", None):
                    almacenes_por_id[asignacion.almacen_id] = asignacion.almacen

        almacenes_unicos = list(almacenes_por_id.values())
        venta.almacen_es_multiple = len(almacenes_unicos) > 1
        venta.almacen_codigo_display = almacenes_unicos[0].codigo if len(almacenes_unicos) == 1 else ""
        venta.almacen_nombre_display = almacenes_unicos[0].nombre if len(almacenes_unicos) == 1 else ""


def get_ventas_list_context(request):
    ventas, filtros = _ventas_filtradas_qs(request)
    ventas = ventas.distinct().annotate(
        total_cantidad=Sum("salida__detalles__cantidad"),
        subtotal_importe=Coalesce(
            Sum(importe_detalles_expr()),
            Value(Decimal("0.00"), output_field=MONEY_FIELD),
        ),
        num_detalle_almacenes=Count("salida__detalles__almacen", distinct=True),
        num_asignacion_almacenes=Count("salida__detalles__asignaciones__almacen", distinct=True),
    ).annotate(total_importe=total_importe_con_comision_expr())

    ventas_activas_ids = list(
        ventas.exclude(estado=NotaVenta.ESTADO_CANCELADA)
        .values_list("salida_id", flat=True)
    )
    resumen = SalidaInventarioDetalle.objects.filter(salida_id__in=ventas_activas_ids).aggregate(
        total_cantidad=Sum("cantidad"),
        subtotal_notas=Sum(importe_linea_expr()),
    )
    resumen_comisiones = NotaVenta.objects.filter(pk__in=ventas_activas_ids).aggregate(
        total_comisiones=Sum("comision_terminal_monto"),
    )

    ventas = ventas.prefetch_related(
        Prefetch("salida__detalles", queryset=_detalle_venta_filtrado_qs(request), to_attr="detalles_filtrados")
    )
    page_obj = Paginator(ventas, 25).get_page(request.GET.get("page"))
    _marcar_almacen_display(page_obj)

    querystring = filtros.copy()
    querystring.pop("page", None)
    total_notas = (resumen["subtotal_notas"] or Decimal("0")) + (
        resumen_comisiones["total_comisiones"] or Decimal("0")
    )

    return {
        "page_obj": page_obj,
        "ventas": page_obj.object_list,
        "productos": Producto.objects.all().order_by("nombre"),
        "almacenes": Almacen.objects.filter(es_activo=True).order_by("tipo", "nombre"),
        "estado_choices": NotaVenta.ESTADO_CHOICES,
        "estado_pago_choices": NotaVenta.ESTADO_PAGO_CHOICES,
        "filtros": filtros,
        "querystring": querystring.urlencode(),
        "total_notas": total_notas,
        "total_cantidad": resumen["total_cantidad"] or Decimal("0"),
    }
