from decimal import Decimal
from datetime import timedelta

from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from accounts.decorators import grupos_requeridos
from django.db.models import Count, DecimalField, ExpressionWrapper, F, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.shortcuts import redirect, render
from django.utils import timezone

from catalogos.models import Almacen, Cliente, ClienteProductoPrecio, Producto, Proveedor
from inventarios.models import EntradaInventario, InventarioStock, SalidaInventario, SalidaInventarioDetalle


ZERO = Decimal("0.00")


def _money(value):
    return (value or ZERO).quantize(Decimal("0.01"))


def _qty(value):
    return (value or ZERO).quantize(Decimal("0.01"))


def _pct(part, total):
    total = total or ZERO
    if total <= 0:
        return ZERO
    return ((part or ZERO) / total * Decimal("100")).quantize(Decimal("0.01"))


def _period_from_request(request):
    allowed = {
        "7": {"label": "Últimos 7 días", "days": 7},
        "30": {"label": "Últimos 30 días", "days": 30},
        "90": {"label": "Últimos 90 días", "days": 90},
    }
    selected = request.GET.get("periodo", "30")
    if selected not in allowed:
        selected = "30"
    today = timezone.localdate()
    start_date = today - timedelta(days=allowed[selected]["days"] - 1)
    return selected, allowed, start_date, today


def _venta_expr():
    return ExpressionWrapper(
        F("cantidad") * F("precio_unitario"),
        output_field=DecimalField(max_digits=16, decimal_places=2),
    )


def _costo_expr():
    return ExpressionWrapper(
        F("cantidad") * F("costo_unitario_aplicado"),
        output_field=DecimalField(max_digits=16, decimal_places=2),
    )


def _utilidad_expr():
    return ExpressionWrapper(
        F("cantidad") * (F("precio_unitario") - F("costo_unitario_aplicado")),
        output_field=DecimalField(max_digits=16, decimal_places=2),
    )


@login_required
def home(request):
    periodo, periodos, fecha_inicio, fecha_fin = _period_from_request(request)

    ventas_activas = SalidaInventario.objects.filter(
        tipo=SalidaInventario.TIPO_VENTA,
        estado=SalidaInventario.ESTADO_ACTIVA,
        fecha__gte=fecha_inicio,
        fecha__lte=fecha_fin,
    )

    detalles_venta = SalidaInventarioDetalle.objects.filter(salida__in=ventas_activas)

    resumen = detalles_venta.aggregate(
        kilos=Coalesce(Sum("cantidad"), Value(ZERO), output_field=DecimalField(max_digits=16, decimal_places=2)),
        venta=Coalesce(Sum(_venta_expr()), Value(ZERO), output_field=DecimalField(max_digits=16, decimal_places=2)),
        costo=Coalesce(Sum(_costo_expr()), Value(ZERO), output_field=DecimalField(max_digits=16, decimal_places=2)),
        utilidad=Coalesce(Sum(_utilidad_expr()), Value(ZERO), output_field=DecimalField(max_digits=16, decimal_places=2)),
    )

    total_venta = _money(resumen["venta"])
    total_costo = _money(resumen["costo"])
    total_utilidad = _money(resumen["utilidad"])
    total_kilos = _qty(resumen["kilos"])

    productos_margen = []
    productos_qs = (
        detalles_venta.values("producto_id", "producto__nombre")
        .annotate(
            kilos=Coalesce(Sum("cantidad"), Value(ZERO), output_field=DecimalField(max_digits=16, decimal_places=2)),
            venta=Coalesce(Sum(_venta_expr()), Value(ZERO), output_field=DecimalField(max_digits=16, decimal_places=2)),
            costo=Coalesce(Sum(_costo_expr()), Value(ZERO), output_field=DecimalField(max_digits=16, decimal_places=2)),
            utilidad=Coalesce(Sum(_utilidad_expr()), Value(ZERO), output_field=DecimalField(max_digits=16, decimal_places=2)),
        )
        .order_by("-utilidad")[:8]
    )
    for item in productos_qs:
        venta = _money(item["venta"])
        utilidad = _money(item["utilidad"])
        productos_margen.append({
            "nombre": item["producto__nombre"],
            "kilos": _qty(item["kilos"]),
            "venta": venta,
            "costo": _money(item["costo"]),
            "utilidad": utilidad,
            "margen": _pct(utilidad, venta),
        })

    mejores_clientes = []
    clientes_qs = (
        detalles_venta.values(
            "salida__cliente",
            "salida__cliente_ref__nombre_fiscal",
            "salida__cliente_ref__nombre_comercial",
        )
        .annotate(
            notas=Count("salida", distinct=True),
            kilos=Coalesce(Sum("cantidad"), Value(ZERO), output_field=DecimalField(max_digits=16, decimal_places=2)),
            venta=Coalesce(Sum(_venta_expr()), Value(ZERO), output_field=DecimalField(max_digits=16, decimal_places=2)),
            utilidad=Coalesce(Sum(_utilidad_expr()), Value(ZERO), output_field=DecimalField(max_digits=16, decimal_places=2)),
        )
        .order_by("-venta")[:8]
    )
    for item in clientes_qs:
        nombre = item["salida__cliente_ref__nombre_comercial"] or item["salida__cliente_ref__nombre_fiscal"] or item["salida__cliente"] or "Cliente sin nombre"
        venta = _money(item["venta"])
        utilidad = _money(item["utilidad"])
        mejores_clientes.append({
            "nombre": nombre,
            "notas": item["notas"],
            "kilos": _qty(item["kilos"]),
            "venta": venta,
            "utilidad": utilidad,
            "margen": _pct(utilidad, venta),
        })

    ventas_credito = ventas_activas.filter(forma_pago_venta=SalidaInventario.FORMA_PAGO_CREDITO)
    credito_ids = list(ventas_credito.values_list("id", flat=True))
    credito_resumen = SalidaInventarioDetalle.objects.filter(salida_id__in=credito_ids).aggregate(
        total=Coalesce(Sum(_venta_expr()), Value(ZERO), output_field=DecimalField(max_digits=16, decimal_places=2))
    )

    hoy = timezone.localdate()
    ventas_hoy = SalidaInventario.objects.filter(
        tipo=SalidaInventario.TIPO_VENTA,
        estado=SalidaInventario.ESTADO_ACTIVA,
        fecha=hoy,
    )
    entradas_hoy = EntradaInventario.objects.filter(fecha=hoy)

    stock_bajo_qs = Producto.objects.filter(
        stock_minimo__gt=0,
        stock__lte=F("stock_minimo"),
    ).order_by("stock", "nombre")[:8]

    productos_sin_costo = Producto.objects.filter(Q(costo_promedio__lte=0) | Q(ultimo_costo_compra__lte=0)).count()
    productos_sin_precio_minimo = Producto.objects.filter(precio_minimo__lte=0).count()

    ultimas_entradas = EntradaInventario.objects.select_related("proveedor", "almacen").order_by("-fecha", "-folio")[:5]
    ultimas_salidas = SalidaInventario.objects.filter(tipo=SalidaInventario.TIPO_VENTA).select_related("cliente_ref", "almacen").order_by("-fecha", "-folio")[:5]

    context = {
        "periodo": periodo,
        "periodos": periodos,
        "fecha_inicio": fecha_inicio,
        "fecha_fin": fecha_fin,
        "ejecutivo": {
            "total_kilos": total_kilos,
            "total_venta": total_venta,
            "total_costo": total_costo,
            "total_utilidad": total_utilidad,
            "margen": _pct(total_utilidad, total_venta),
            "notas": ventas_activas.count(),
            "ticket_promedio": _money(total_venta / ventas_activas.count()) if ventas_activas.count() else ZERO,
            "productos_margen": productos_margen,
            "mejores_clientes": mejores_clientes,
            "credito_notas": ventas_credito.count(),
            "credito_total": _money(credito_resumen["total"]),
        },
        "operativo": {
            "ventas_hoy": ventas_hoy.count(),
            "entradas_hoy": entradas_hoy.count(),
            "productos_activos": Producto.objects.count(),
            "clientes_activos": Cliente.objects.filter(activo=True).count(),
            "proveedores_activos": Proveedor.objects.filter(activo=True).count(),
            "almacenes_activos": Almacen.objects.filter(es_activo=True).count(),
            "stock_bajo_total": Producto.objects.filter(stock_minimo__gt=0, stock__lte=F("stock_minimo")).count(),
            "stock_bajo": stock_bajo_qs,
            "productos_sin_costo": productos_sin_costo,
            "productos_sin_precio_minimo": productos_sin_precio_minimo,
            "precios_cliente": ClienteProductoPrecio.objects.count(),
            "stocks_por_almacen": InventarioStock.objects.count(),
            "ultimas_entradas": ultimas_entradas,
            "ultimas_salidas": ultimas_salidas,
        },
    }
    return render(request, "accounts/home.html", context)


@login_required
def logout_view(request):
    """
    Cierra la sesión del usuario y lo redirige a la pantalla de login.
    """
    logout(request)
    return redirect("login")


@grupos_requeridos("Catalogos", "Administrador")
@login_required
def productos_list(request):
    return render(request, 'catalogos/productos_list.html')


@grupos_requeridos("Catalogos", "Administrador")
@login_required
def productos_form(request):
    return render(request, "catalogos/productos_form.html")
