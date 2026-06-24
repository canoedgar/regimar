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
from inventarios.models import EntradaInventario, InventarioStock
from ventas.models import NotaVenta, NotaVentaDetalle


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
    """
    Dashboard controlado por permisos del rol.

    La visibilidad no se resuelve solo en el template: también se evita calcular y enviar
    información al contexto cuando el usuario no tiene permiso de lectura sobre el
    recurso correspondiente.
    """
    user = request.user

    def puede(*permisos):
        return any(user.has_perm(permiso) for permiso in permisos)

    dashboard_permisos = {
        "ventas_ver": puede("ventas.view_notaventa"),
        "ventas_agregar": puede("ventas.add_notaventa"),
        "entradas_ver": puede("inventarios.view_entradainventario"),
        "entradas_agregar": puede("inventarios.add_entradainventario"),
        "inventario_ver": puede("inventarios.view_inventariostock"),
        "inventario_ajustar": puede("inventarios.change_inventariostock"),
        "productos_ver": puede("catalogos.view_producto"),
        "clientes_ver": puede("catalogos.view_cliente"),
        "clientes_agregar": puede("catalogos.add_cliente"),
        "proveedores_ver": puede("catalogos.view_proveedor"),
        "almacenes_ver": puede("catalogos.view_almacen"),
        "precios_cliente_ver": puede("catalogos.view_clienteproductoprecio"),
        "cotizaciones_ver": puede("cotizaciones.view_cotizacionprecio"),
        "cotizaciones_agregar": puede("cotizaciones.add_cotizacionprecio"),
        "cartera_ver": puede("cartera.view_pagocliente"),
        "cartera_agregar": puede("cartera.add_pagocliente"),
    }
    dashboard_permisos["ejecutivo_ver"] = dashboard_permisos["ventas_ver"]
    dashboard_permisos["operativo_ver"] = any([
        dashboard_permisos["ventas_ver"],
        dashboard_permisos["ventas_agregar"],
        dashboard_permisos["entradas_ver"],
        dashboard_permisos["entradas_agregar"],
        dashboard_permisos["inventario_ver"],
        dashboard_permisos["inventario_ajustar"],
        dashboard_permisos["productos_ver"],
        dashboard_permisos["clientes_ver"],
        dashboard_permisos["clientes_agregar"],
        dashboard_permisos["proveedores_ver"],
        dashboard_permisos["almacenes_ver"],
        dashboard_permisos["cotizaciones_ver"],
        dashboard_permisos["cotizaciones_agregar"],
        dashboard_permisos["cartera_ver"],
        dashboard_permisos["cartera_agregar"],
    ])
    dashboard_permisos["alertas_operacion_ver"] = any([
        dashboard_permisos["inventario_ver"],
        dashboard_permisos["productos_ver"],
    ])
    dashboard_permisos["ultimos_movimientos_ver"] = any([
        dashboard_permisos["entradas_ver"],
        dashboard_permisos["ventas_ver"],
    ])
    dashboard_permisos["accesos_rapidos_ver"] = any([
        dashboard_permisos["ventas_agregar"],
        dashboard_permisos["ventas_ver"],
        dashboard_permisos["entradas_agregar"],
        dashboard_permisos["inventario_ajustar"],
        dashboard_permisos["inventario_ver"],
        dashboard_permisos["clientes_agregar"],
    ])

    periodo, periodos, fecha_inicio, fecha_fin = _period_from_request(request)
    hoy = timezone.localdate()

    ejecutivo = {
        "total_kilos": ZERO,
        "total_venta": ZERO,
        "total_costo": ZERO,
        "total_utilidad": ZERO,
        "margen": ZERO,
        "notas": 0,
        "ticket_promedio": ZERO,
        "productos_margen": [],
        "mejores_clientes": [],
        "credito_notas": 0,
        "credito_total": ZERO,
    }
    operativo = {
        "ventas_hoy": 0,
        "entradas_hoy": 0,
        "productos_activos": 0,
        "clientes_activos": 0,
        "proveedores_activos": 0,
        "almacenes_activos": 0,
        "stock_bajo_total": 0,
        "stock_bajo": [],
        "productos_sin_costo": 0,
        "productos_sin_precio_minimo": 0,
        "precios_cliente": 0,
        "stocks_por_almacen": 0,
        "ultimas_entradas": [],
        "ultimas_salidas": [],
    }

    ventas_activas = NotaVenta.objects.none()
    detalles_venta = NotaVentaDetalle.objects.none()

    if dashboard_permisos["ventas_ver"]:
        ventas_activas = NotaVenta.objects.filter(
            tipo=NotaVenta.TIPO_VENTA,
            estado=NotaVenta.ESTADO_ACTIVA,
            fecha__gte=fecha_inicio,
            fecha__lte=fecha_fin,
        )
        detalles_venta = NotaVentaDetalle.objects.filter(salida__in=ventas_activas)

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
        notas_count = ventas_activas.count()

        ejecutivo.update({
            "total_kilos": total_kilos,
            "total_venta": total_venta,
            "total_costo": total_costo,
            "total_utilidad": total_utilidad,
            "margen": _pct(total_utilidad, total_venta),
            "notas": notas_count,
            "ticket_promedio": _money(total_venta / notas_count) if notas_count else ZERO,
        })

        if dashboard_permisos["productos_ver"]:
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
            productos_margen = []
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
            ejecutivo["productos_margen"] = productos_margen

        if dashboard_permisos["clientes_ver"]:
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
            mejores_clientes = []
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
            ejecutivo["mejores_clientes"] = mejores_clientes

        if dashboard_permisos["cartera_ver"]:
            ventas_credito = ventas_activas.filter(forma_pago_venta=NotaVenta.FORMA_PAGO_CREDITO)
            credito_ids = list(ventas_credito.values_list("id", flat=True))
            credito_resumen = NotaVentaDetalle.objects.filter(salida_id__in=credito_ids).aggregate(
                total=Coalesce(Sum(_venta_expr()), Value(ZERO), output_field=DecimalField(max_digits=16, decimal_places=2))
            )
            ejecutivo["credito_notas"] = ventas_credito.count()
            ejecutivo["credito_total"] = _money(credito_resumen["total"])

        operativo["ventas_hoy"] = NotaVenta.objects.filter(
            tipo=NotaVenta.TIPO_VENTA,
            estado=NotaVenta.ESTADO_ACTIVA,
            fecha=hoy,
        ).count()
        operativo["ultimas_salidas"] = (
            NotaVenta.objects.filter(tipo=NotaVenta.TIPO_VENTA)
            .select_related("cliente_ref", "almacen")
            .order_by("-fecha", "-folio")[:5]
        )

    if dashboard_permisos["entradas_ver"]:
        operativo["entradas_hoy"] = EntradaInventario.objects.filter(fecha=hoy).count()
        operativo["ultimas_entradas"] = (
            EntradaInventario.objects.select_related("proveedor", "almacen")
            .order_by("-fecha", "-folio")[:5]
        )

    if dashboard_permisos["productos_ver"]:
        operativo["productos_activos"] = Producto.objects.count()
        operativo["productos_sin_costo"] = Producto.objects.filter(Q(costo_promedio__lte=0) | Q(ultimo_costo_compra__lte=0)).count()
        operativo["productos_sin_precio_minimo"] = Producto.objects.filter(precio_minimo__lte=0).count()

    if dashboard_permisos["inventario_ver"]:
        stock_bajo_qs = Producto.objects.filter(
            stock_minimo__gt=0,
            stock__lte=F("stock_minimo"),
        ).order_by("stock", "nombre")[:8]
        operativo["stock_bajo_total"] = Producto.objects.filter(stock_minimo__gt=0, stock__lte=F("stock_minimo")).count()
        operativo["stock_bajo"] = stock_bajo_qs
        operativo["stocks_por_almacen"] = InventarioStock.objects.count()

    if dashboard_permisos["clientes_ver"]:
        operativo["clientes_activos"] = Cliente.objects.filter(activo=True).count()

    if dashboard_permisos["proveedores_ver"]:
        operativo["proveedores_activos"] = Proveedor.objects.filter(activo=True).count()

    if dashboard_permisos["almacenes_ver"]:
        operativo["almacenes_activos"] = Almacen.objects.filter(es_activo=True).count()

    if dashboard_permisos["precios_cliente_ver"]:
        operativo["precios_cliente"] = ClienteProductoPrecio.objects.count()

    context = {
        "periodo": periodo,
        "periodos": periodos,
        "fecha_inicio": fecha_inicio,
        "fecha_fin": fecha_fin,
        "dashboard_permisos": dashboard_permisos,
        "ejecutivo": ejecutivo,
        "operativo": operativo,
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
