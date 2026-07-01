from decimal import Decimal

from django.db.models import Count, DecimalField, Max, Q, Sum, Value
from django.db.models.functions import Coalesce

from cartera.models import FacturaAplicacionNota, FacturaCliente

MONEY_FIELD = DecimalField(max_digits=14, decimal_places=2)
ZERO = Value(Decimal("0.00"), output_field=MONEY_FIELD)


def get_facturas_cliente(cliente, incluir_canceladas=True):
    qs = (
        FacturaCliente.objects.filter(cliente=cliente)
        .select_related("cliente", "creado_por", "cancelado_por")
        .prefetch_related("aplicaciones__nota_venta")
        .order_by("-fecha", "-id")
    )
    if not incluir_canceladas:
        qs = qs.filter(estado=FacturaCliente.ESTADO_ACTIVA)
    return qs


def get_facturacion_cliente_resumen(cliente):
    facturas = FacturaCliente.objects.filter(cliente=cliente)
    activos = facturas.filter(estado=FacturaCliente.ESTADO_ACTIVA)
    cancelados = facturas.filter(estado=FacturaCliente.ESTADO_CANCELADA)
    return {
        "total_facturado_activo": activos.aggregate(total=Coalesce(Sum("total"), ZERO))["total"],
        "total_cancelado": cancelados.aggregate(total=Coalesce(Sum("total"), ZERO))["total"],
        "total_global": activos.filter(tipo_aplicacion=FacturaCliente.TIPO_GLOBAL).aggregate(total=Coalesce(Sum("total"), ZERO))["total"],
        "total_notas": activos.filter(tipo_aplicacion=FacturaCliente.TIPO_NOTAS).aggregate(total=Coalesce(Sum("total"), ZERO))["total"],
        "cantidad_facturas": facturas.count(),
        "cantidad_activas": activos.count(),
        "ultimo_cfdi": facturas.order_by("-fecha", "-id").first(),
    }


def get_facturas_nota(nota, incluir_canceladas=True):
    qs = (
        FacturaAplicacionNota.objects.filter(nota_venta=nota)
        .select_related("factura", "factura__cliente")
        .order_by("-factura__fecha", "-factura_id")
    )
    if not incluir_canceladas:
        qs = qs.filter(factura__estado=FacturaCliente.ESTADO_ACTIVA)
    return qs


def get_total_facturado_nota(nota):
    return get_facturas_nota(nota, incluir_canceladas=False).aggregate(
        total=Coalesce(Sum("monto_facturado"), ZERO)
    )["total"]


def get_reporte_facturacion_por_cliente(fecha_inicio=None, fecha_fin=None, cliente_query="", estado="", tipo_aplicacion=""):
    qs = FacturaCliente.objects.select_related("cliente").prefetch_related("aplicaciones__nota_venta")
    if fecha_inicio:
        qs = qs.filter(fecha__date__gte=fecha_inicio)
    if fecha_fin:
        qs = qs.filter(fecha__date__lte=fecha_fin)
    if estado in {FacturaCliente.ESTADO_ACTIVA, FacturaCliente.ESTADO_CANCELADA}:
        qs = qs.filter(estado=estado)
    if tipo_aplicacion in {FacturaCliente.TIPO_GLOBAL, FacturaCliente.TIPO_NOTAS}:
        qs = qs.filter(tipo_aplicacion=tipo_aplicacion)
    if cliente_query:
        qs = qs.filter(
            Q(cliente__nombre_fiscal__icontains=cliente_query)
            | Q(cliente__nombre_comercial__icontains=cliente_query)
            | Q(cliente__rfc__icontains=cliente_query)
            | Q(rfc_receptor__icontains=cliente_query)
            | Q(nombre_receptor__icontains=cliente_query)
            | Q(uuid__icontains=cliente_query)
            | Q(serie__icontains=cliente_query)
            | Q(folio__icontains=cliente_query)
        )
    return qs.order_by("cliente__nombre_fiscal", "cliente__nombre_comercial", "-fecha", "-id")


def get_reporte_facturacion_resumen(qs):
    return {
        "total_activo": qs.filter(estado=FacturaCliente.ESTADO_ACTIVA).aggregate(total=Coalesce(Sum("total"), ZERO))["total"],
        "total_cancelado": qs.filter(estado=FacturaCliente.ESTADO_CANCELADA).aggregate(total=Coalesce(Sum("total"), ZERO))["total"],
        "total_global": qs.filter(estado=FacturaCliente.ESTADO_ACTIVA, tipo_aplicacion=FacturaCliente.TIPO_GLOBAL).aggregate(total=Coalesce(Sum("total"), ZERO))["total"],
        "total_notas": qs.filter(estado=FacturaCliente.ESTADO_ACTIVA, tipo_aplicacion=FacturaCliente.TIPO_NOTAS).aggregate(total=Coalesce(Sum("total"), ZERO))["total"],
        "cantidad": qs.count(),
        "clientes": qs.values("cliente_id").distinct().count(),
    }


def get_reporte_facturacion_resumen_clientes(qs):
    return (
        qs.values("cliente_id", "cliente__nombre_fiscal", "cliente__nombre_comercial", "cliente__rfc")
        .annotate(
            total_activo=Coalesce(Sum("total", filter=Q(estado=FacturaCliente.ESTADO_ACTIVA)), ZERO),
            total_cancelado=Coalesce(Sum("total", filter=Q(estado=FacturaCliente.ESTADO_CANCELADA)), ZERO),
            total_global=Coalesce(Sum("total", filter=Q(estado=FacturaCliente.ESTADO_ACTIVA, tipo_aplicacion=FacturaCliente.TIPO_GLOBAL)), ZERO),
            total_notas=Coalesce(Sum("total", filter=Q(estado=FacturaCliente.ESTADO_ACTIVA, tipo_aplicacion=FacturaCliente.TIPO_NOTAS)), ZERO),
            facturas=Count("id"),
            ultima_factura=Max("fecha"),
        )
        .order_by("cliente__nombre_fiscal", "cliente__nombre_comercial")
    )


def get_estado_facturacion_cliente(cliente):
    facturas = get_facturas_cliente(cliente, incluir_canceladas=True)
    return {
        "resumen": get_facturacion_cliente_resumen(cliente),
        "facturas": facturas,
    }


def get_kpis_facturacion():
    facturas = FacturaCliente.objects.all()
    return facturas.aggregate(
        total_activo=Coalesce(Sum("total", filter=Q(estado=FacturaCliente.ESTADO_ACTIVA)), ZERO),
        total_cancelado=Coalesce(Sum("total", filter=Q(estado=FacturaCliente.ESTADO_CANCELADA)), ZERO),
        cantidad=Count("id"),
        ultimo=Max("fecha"),
    )
