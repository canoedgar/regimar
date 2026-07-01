from datetime import datetime, time, timedelta
from decimal import Decimal

from django.db.models import Count, DecimalField, ExpressionWrapper, F, Sum, Value
from django.db.models.functions import Coalesce
from django.template.loader import render_to_string
from django.utils import timezone

from catalogos.models import Cliente, ParametroSistema, Producto
from cartera.models import ClienteSaldoFavorMovimiento, PagoCliente
from cartera.selectors.cartera import get_notas_venta_con_totales, get_saldo_favor_cliente, get_total_adeudado_cliente
from inventarios.models import EntradaInventario, EntradaInventarioDetalle, InventarioStock, SalidaInventario
from ventas.models import NotaVenta, NotaVentaDetalle
from notificaciones.models import NotificacionCorreo
from notificaciones.services.correo import enviar_correo

MONEY_FIELD = DecimalField(max_digits=14, decimal_places=2)
QTY_FIELD = DecimalField(max_digits=14, decimal_places=2)
ZERO_MONEY = Value(Decimal("0.00"), output_field=MONEY_FIELD)
ZERO_QTY = Value(Decimal("0.00"), output_field=QTY_FIELD)


def _local_datetime_range(fecha_inicio, fecha_fin):
    tz = timezone.get_current_timezone()
    inicio = timezone.make_aware(datetime.combine(fecha_inicio, time.min), tz)
    fin = timezone.make_aware(datetime.combine(fecha_fin, time.max), tz)
    return inicio, fin


def _date_range(fecha_inicio=None, fecha_fin=None):
    hoy = timezone.localdate()
    fecha_inicio = fecha_inicio or hoy
    fecha_fin = fecha_fin or fecha_inicio
    return fecha_inicio, fecha_fin


def _empresa_contexto():
    return {
        "nombre": ParametroSistema.objects.filter(clave="EMPRESA_NOMBRE", activo=True).values_list("valor", flat=True).first() or "Regimar",
        "email": ParametroSistema.objects.filter(clave="EMPRESA_EMAIL", activo=True).values_list("valor", flat=True).first() or "",
        "telefono": ParametroSistema.objects.filter(clave="EMPRESA_TELEFONO", activo=True).values_list("valor", flat=True).first() or "",
    }


def _money_sum(qs, expression):
    return qs.aggregate(total=Coalesce(Sum(expression), ZERO_MONEY))["total"] or Decimal("0.00")


def _qty_sum(qs, field_name="cantidad"):
    return qs.aggregate(total=Coalesce(Sum(field_name), ZERO_QTY))["total"] or Decimal("0.00")


def _map_tipo(modelo, tipo):
    return dict(modelo.TIPO_CHOICES).get(tipo, tipo or "Sin tipo")


def _importe_entrada_expr():
    return ExpressionWrapper(F("cantidad") * F("costo_unitario"), output_field=MONEY_FIELD)


def _importe_salida_expr():
    return ExpressionWrapper(F("cantidad") * F("precio_unitario"), output_field=MONEY_FIELD)


def _costo_salida_expr():
    return ExpressionWrapper(F("cantidad") * F("costo_unitario_aplicado"), output_field=MONEY_FIELD)


def construir_reporte_general(fecha_inicio=None, fecha_fin=None):
    """Construye el reporte operativo general sin enviar correos.

    Incluye inventario, ventas y cartera/pagos aplicados para el rango recibido.
    """
    fecha_inicio, fecha_fin = _date_range(fecha_inicio, fecha_fin)
    inicio_dt, fin_dt = _local_datetime_range(fecha_inicio, fecha_fin)

    entradas = EntradaInventario.objects.filter(fecha__range=(fecha_inicio, fecha_fin))
    entradas_detalle = EntradaInventarioDetalle.objects.filter(entrada__in=entradas)
    ventas = NotaVenta.objects.filter(
        estado=NotaVenta.ESTADO_ACTIVA,
        fecha__range=(fecha_inicio, fecha_fin),
    )
    ventas_detalle = NotaVentaDetalle.objects.filter(salida__in=ventas)
    pagos = PagoCliente.objects.filter(
        estado=PagoCliente.ESTADO_ACTIVO,
        fecha__gte=inicio_dt,
        fecha__lte=fin_dt,
    )
    pagos_cancelados = PagoCliente.objects.filter(
        estado=PagoCliente.ESTADO_CANCELADO,
        cancelado_en__gte=inicio_dt,
        cancelado_en__lte=fin_dt,
    )
    movimientos_saldo_favor = ClienteSaldoFavorMovimiento.objects.filter(fecha__gte=inicio_dt, fecha__lte=fin_dt)

    importe_ventas = _money_sum(ventas_detalle, _importe_salida_expr())
    costo_ventas = _money_sum(ventas_detalle, _costo_salida_expr())
    margen_ventas = importe_ventas - costo_ventas

    total_cartera = Decimal("0.00")
    total_saldo_favor = Decimal("0.00")
    clientes_con_saldo = 0
    for cliente in Cliente.objects.filter(activo=True).only("id"):
        adeudo = get_total_adeudado_cliente(cliente)
        saldo_favor = get_saldo_favor_cliente(cliente)
        total_cartera += adeudo
        total_saldo_favor += saldo_favor
        if adeudo > 0 or saldo_favor > 0:
            clientes_con_saldo += 1

    notas_pendientes = list(get_notas_venta_con_totales().filter(saldo_pendiente__gt=0))
    total_notas_pendientes = len(notas_pendientes)
    importe_notas_pendientes = sum((nota.saldo_pendiente for nota in notas_pendientes), Decimal("0.00"))

    stock_total = InventarioStock.objects.aggregate(total=Coalesce(Sum("cantidad"), ZERO_QTY))["total"] or Decimal("0.00")
    productos_con_stock = InventarioStock.objects.filter(cantidad__gt=0).values("producto_id").distinct().count()
    productos_bajos_qs = (
        Producto.objects.annotate(stock_actual=Coalesce(Sum("stocks__cantidad"), ZERO_QTY))
        .filter(stock_minimo__gt=0, stock_actual__lte=F("stock_minimo"))
        .order_by("stock_actual", "nombre")
    )

    entradas_por_tipo = list(
        entradas.values("tipo")
        .annotate(
            movimientos=Count("id", distinct=True),
            cantidad=Coalesce(Sum("detalles__cantidad"), ZERO_QTY),
            importe=Coalesce(Sum(ExpressionWrapper(F("detalles__cantidad") * F("detalles__costo_unitario"), output_field=MONEY_FIELD)), ZERO_MONEY),
        )
        .order_by("tipo")
    )
    for item in entradas_por_tipo:
        item["tipo_label"] = _map_tipo(EntradaInventario, item["tipo"])

    salidas_por_tipo = list(
        SalidaInventario.objects.filter(fecha__range=(fecha_inicio, fecha_fin), estado=SalidaInventario.ESTADO_ACTIVA)
        .values("tipo")
        .annotate(
            movimientos=Count("id", distinct=True),
            cantidad=Coalesce(Sum("detalles__cantidad"), ZERO_QTY),
            importe=Coalesce(Sum(ExpressionWrapper(F("detalles__cantidad") * F("detalles__precio_unitario"), output_field=MONEY_FIELD)), ZERO_MONEY),
        )
        .order_by("tipo")
    )
    for item in salidas_por_tipo:
        item["tipo_label"] = _map_tipo(SalidaInventario, item["tipo"])

    ventas_por_cliente = list(
        ventas.values("cliente_ref_id", "cliente_ref__nombre_fiscal", "cliente_ref__nombre_comercial", "cliente")
        .annotate(
            notas=Count("id", distinct=True),
            importe=Coalesce(Sum(ExpressionWrapper(F("detalles__cantidad") * F("detalles__precio_unitario"), output_field=MONEY_FIELD)), ZERO_MONEY),
        )
        .order_by("-importe")[:10]
    )

    pagos_por_cliente = list(
        pagos.values("cliente_id", "cliente__nombre_fiscal", "cliente__nombre_comercial")
        .annotate(pagos=Count("id"), importe=Coalesce(Sum("monto_recibido"), ZERO_MONEY))
        .order_by("-importe")[:10]
    )

    productos_bajos = list(productos_bajos_qs.values("nombre", "metrica", "stock_minimo", "stock_actual")[:10])

    return {
        "empresa": _empresa_contexto(),
        "fecha_inicio": fecha_inicio,
        "fecha_fin": fecha_fin,
        "generado_en": timezone.localtime(),
        "inventario": {
            "stock_total": stock_total,
            "productos_con_stock": productos_con_stock,
            "productos_bajos_count": productos_bajos_qs.count(),
            "productos_bajos": productos_bajos,
            "entradas_count": entradas.count(),
            "entradas_cantidad": _qty_sum(entradas_detalle),
            "entradas_importe": _money_sum(entradas_detalle, _importe_entrada_expr()),
            "entradas_por_tipo": entradas_por_tipo,
            "salidas_por_tipo": salidas_por_tipo,
        },
        "ventas": {
            "notas_count": ventas.count(),
            "unidades": _qty_sum(ventas_detalle),
            "importe": importe_ventas,
            "costo": costo_ventas,
            "margen": margen_ventas,
            "ventas_por_cliente": ventas_por_cliente,
        },
        "cartera": {
            "pagos_count": pagos.count(),
            "pagos_importe": pagos.aggregate(total=Coalesce(Sum("monto_recibido"), ZERO_MONEY))["total"] or Decimal("0.00"),
            "pagos_cancelados_count": pagos_cancelados.count(),
            "pagos_cancelados_importe": pagos_cancelados.aggregate(total=Coalesce(Sum("monto_recibido"), ZERO_MONEY))["total"] or Decimal("0.00"),
            "saldo_favor_generado": movimientos_saldo_favor.filter(tipo=ClienteSaldoFavorMovimiento.TIPO_GENERACION).aggregate(total=Coalesce(Sum("monto"), ZERO_MONEY))["total"] or Decimal("0.00"),
            "saldo_favor_aplicado": movimientos_saldo_favor.filter(tipo=ClienteSaldoFavorMovimiento.TIPO_APLICACION).aggregate(total=Coalesce(Sum("monto"), ZERO_MONEY))["total"] or Decimal("0.00"),
            "saldo_favor_devuelto": movimientos_saldo_favor.filter(tipo=ClienteSaldoFavorMovimiento.TIPO_DEVOLUCION).aggregate(total=Coalesce(Sum("monto"), ZERO_MONEY))["total"] or Decimal("0.00"),
            "total_cartera": total_cartera,
            "total_saldo_favor": total_saldo_favor,
            "clientes_con_saldo": clientes_con_saldo,
            "notas_pendientes_count": total_notas_pendientes,
            "notas_pendientes_importe": importe_notas_pendientes,
            "pagos_por_cliente": pagos_por_cliente,
        },
    }


def construir_asunto_reporte_general(reporte):
    fecha_inicio = reporte["fecha_inicio"].isoformat()
    fecha_fin = reporte["fecha_fin"].isoformat()
    if fecha_inicio == fecha_fin:
        rango = fecha_inicio
    else:
        rango = f"{fecha_inicio} a {fecha_fin}"
    return f"Reporte general Regimar | {rango}"


def construir_cuerpo_texto_reporte_general(reporte):
    inv = reporte["inventario"]
    ventas = reporte["ventas"]
    cartera = reporte["cartera"]
    return "\n".join([
        construir_asunto_reporte_general(reporte),
        "",
        f"Inventario: {inv['entradas_count']} entradas, {inv['productos_bajos_count']} productos en mínimo o bajo mínimo.",
        f"Ventas: {ventas['notas_count']} notas por ${ventas['importe']:.2f}. Margen estimado ${ventas['margen']:.2f}.",
        f"Pagos: {cartera['pagos_count']} pagos activos por ${cartera['pagos_importe']:.2f}.",
        f"Cartera actual: ${cartera['total_cartera']:.2f} por cobrar, ${cartera['total_saldo_favor']:.2f} en saldo a favor.",
        "",
        "Este correo fue generado automáticamente desde el módulo de notificaciones.",
    ])


def enviar_reporte_general_por_correo(fecha_inicio=None, fecha_fin=None, destinatarios=None, usuario=None):
    reporte = construir_reporte_general(fecha_inicio=fecha_inicio, fecha_fin=fecha_fin)
    asunto = construir_asunto_reporte_general(reporte)
    cuerpo_texto = construir_cuerpo_texto_reporte_general(reporte)
    cuerpo_html = render_to_string("notificaciones/emails/reporte_general.html", {"reporte": reporte})
    return enviar_correo(
        asunto=asunto,
        destinatarios=destinatarios,
        cuerpo_texto=cuerpo_texto,
        cuerpo_html=cuerpo_html,
        tipo=NotificacionCorreo.TIPO_REPORTE_GENERAL,
        usuario=usuario,
        metadata={
            "fecha_inicio": reporte["fecha_inicio"].isoformat(),
            "fecha_fin": reporte["fecha_fin"].isoformat(),
        },
    )


def rango_por_dias(dias_a_reportar=0):
    hoy = timezone.localdate()
    dias_a_reportar = int(dias_a_reportar or 0)
    if dias_a_reportar <= 0:
        return hoy, hoy

    fecha_fin = hoy - timedelta(days=1)
    fecha_inicio = hoy - timedelta(days=dias_a_reportar)
    return fecha_inicio, fecha_fin
