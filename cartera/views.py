from datetime import date
from decimal import Decimal

from django.contrib import messages
from django.http import FileResponse, Http404
from django.contrib.auth.decorators import login_required
from accounts.decorators import grupos_requeridos, permiso_requerido
from django.core.exceptions import ValidationError
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from catalogos.models import Cliente, ParametroSistema
from ventas.models import NotaVenta
from cartera.forms import (
    CancelarFacturaForm,
    CancelarPagoForm,
    FacturaAplicacionNotaFormSet,
    FacturaClienteForm,
    PagoGlobalForm,
    PagoNotaForm,
    ReporteFacturacionForm,
    SaldoFavorAplicacionForm,
    SaldoFavorDevolucionForm,
)
from cartera.models import ClienteSaldoFavorMovimiento, FacturaCliente, PagoAplicacionNota, PagoCliente
from cartera.selectors.cartera import (
    get_estado_cuenta_cliente,
    get_notas_con_saldo_pendiente,
    get_saldo_favor_cliente,
    get_saldo_pendiente_nota,
    get_total_adeudado_cliente,
    get_total_nota,
)
from cartera.selectors.facturacion import (
    get_estado_facturacion_cliente,
    get_facturacion_cliente_resumen,
    get_facturas_cliente,
    get_reporte_facturacion_por_cliente,
    get_reporte_facturacion_resumen,
    get_reporte_facturacion_resumen_clientes,
)
from cartera.services.cartera import aplicar_saldo_favor_a_nota, cancelar_pago_cliente, devolver_saldo_favor, registrar_pago_fifo, registrar_pago_notas_especificas
from cartera.services.facturacion import cancelar_factura_cliente, pretty_xml_factura, registrar_factura_cliente


def _puede_registrar_pagos(user):
    return (
        user.is_superuser
        or user.has_perm("cartera.puede_registrar_pagos")
        or user.groups.filter(name__in=["Ventas", "Administrador"]).exists()
    )




def _puede_registrar_facturas(user):
    return (
        user.is_superuser
        or user.has_perm("cartera.puede_registrar_facturas")
        or user.has_perm("cartera.add_facturacliente")
        or user.groups.filter(name__in=["Ventas", "Administrador"]).exists()
    )


def _puede_ver_facturacion(user):
    return (
        user.is_superuser
        or user.has_perm("cartera.puede_ver_facturacion")
        or user.has_perm("cartera.view_facturacliente")
        or user.groups.filter(name__in=["Ventas", "Administrador"]).exists()
    )


def _puede_cancelar_facturas(user):
    return (
        user.is_superuser
        or user.has_perm("cartera.puede_cancelar_facturas")
        or user.has_perm("cartera.change_facturacliente")
    )


def _puede_cancelar_pagos(user):
    return (
        user.is_superuser
        or user.has_perm("cartera.puede_cancelar_pagos")
        or user.has_perm("cartera.change_pagocliente")
    )


def _buscar_clientes(query, limit=12):
    clientes = Cliente.objects.filter(activo=True).order_by("nombre_fiscal", "nombre_comercial", "id")
    if query:
        clientes = clientes.filter(
            Q(nombre_fiscal__icontains=query)
            | Q(nombre_comercial__icontains=query)
            | Q(rfc__icontains=query)
            | Q(telefono__icontains=query)
            | Q(contacto__icontains=query)
        )
    return clientes[:limit]


def _filtrar_clientes_estado_cuenta(query, filtro_estado="todos", limit=20):
    clientes = _buscar_clientes(query, limit=80) if query else Cliente.objects.none()
    resultados = []

    for cliente in clientes:
        adeudo = get_total_adeudado_cliente(cliente)
        saldo_favor = get_saldo_favor_cliente(cliente)

        if filtro_estado == "saldo_pendiente" and adeudo <= 0:
            continue
        if filtro_estado == "saldo_favor" and saldo_favor <= 0:
            continue
        if filtro_estado == "sin_saldo" and (adeudo > 0 or saldo_favor > 0):
            continue

        resultados.append({
            "cliente": cliente,
            "adeudo": adeudo,
            "saldo_favor": saldo_favor,
        })

        if len(resultados) >= limit:
            break

    return resultados


def _get_movimientos_limit(request):
    valor = (request.GET.get("movimientos") or "10").strip().lower()
    opciones = ["10", "20", "30", "50", "100", "todos"]
    if valor not in opciones:
        valor = "10"
    return valor, None if valor == "todos" else int(valor)


def _get_cantidad_reporte(request, default="todos"):
    opciones = ["10", "20", "30", "50", "100", "todos"]
    valor = (request.GET.get("cantidad") or default).strip().lower()
    if valor not in opciones:
        valor = default if default in opciones else "todos"
    return valor, None if valor == "todos" else int(valor), opciones


def _empresa_contexto():
    return {
        "nombre": ParametroSistema.objects.filter(clave="EMPRESA_NOMBRE", activo=True).values_list("valor", flat=True).first() or "Regimar",
        "propietario": ParametroSistema.objects.filter(clave="EMPRESA_PROPIETARIO", activo=True).values_list("valor", flat=True).first() or "Regimar",
        "direccion": ParametroSistema.objects.filter(clave="EMPRESA_DIRECCION", activo=True).values_list("valor", flat=True).first() or "Calle Sinaloa 737, Zona Norte, Ciudad Obregon, Sonora CP 85000",
        "telefono": ParametroSistema.objects.filter(clave="EMPRESA_TELEFONO", activo=True).values_list("valor", flat=True).first() or "686 162 7239",
        "email": ParametroSistema.objects.filter(clave="EMPRESA_EMAIL", activo=True).values_list("valor", flat=True).first() or "regimar@gmail.com",
    }


@permiso_requerido("cartera.view_pagocliente", "ventas.view_notaventa", "inventarios.view_salidainventario")
def cartera_dashboard(request):
    query = (request.GET.get("q") or "").strip()
    estado_query = (request.GET.get("estado_q") or "").strip()
    estado_filtro = (request.GET.get("estado_filtro") or "todos").strip()
    if estado_filtro not in ["todos", "saldo_pendiente", "saldo_favor", "sin_saldo"]:
        estado_filtro = "todos"
    clientes_estado_encontrados = _filtrar_clientes_estado_cuenta(estado_query, filtro_estado=estado_filtro, limit=20) if estado_query else []

    clientes = Cliente.objects.filter(activo=True).order_by("nombre_fiscal", "nombre_comercial")
    if query:
        clientes = clientes.filter(
            Q(nombre_fiscal__icontains=query)
            | Q(nombre_comercial__icontains=query)
            | Q(rfc__icontains=query)
            | Q(telefono__icontains=query)
            | Q(contacto__icontains=query)
        )

    resumen_clientes = []
    total_cartera = Decimal("0.00")
    total_saldo_favor = Decimal("0.00")

    for cliente in clientes[:100]:
        adeudo = get_total_adeudado_cliente(cliente)
        saldo_favor = get_saldo_favor_cliente(cliente)
        if adeudo > 0 or saldo_favor > 0 or query:
            resumen_clientes.append({"cliente": cliente, "adeudo": adeudo, "saldo_favor": saldo_favor})
            total_cartera += adeudo
            total_saldo_favor += saldo_favor

    pagos_hoy = PagoCliente.objects.filter(
        estado=PagoCliente.ESTADO_ACTIVO,
        fecha__date=timezone.localdate(),
    ).aggregate(total=Sum("monto_recibido"))["total"] or Decimal("0.00")

    return render(
        request,
        "cartera/dashboard.html",
        {
            "query": query,
            "estado_query": estado_query,
            "estado_filtro": estado_filtro,
            "clientes_estado_encontrados": clientes_estado_encontrados,
            "resumen_clientes": resumen_clientes,
            "total_cartera": total_cartera,
            "total_saldo_favor": total_saldo_favor,
            "pagos_hoy": pagos_hoy,
            "puede_registrar_pagos": _puede_registrar_pagos(request.user),
            "puede_registrar_facturas": _puede_registrar_facturas(request.user),
            "puede_ver_facturacion": _puede_ver_facturacion(request.user),
        },
    )


def _facturacion_activa(request):
    return (request.GET.get("facturacion") or "").strip() in {"1", "true", "on", "si", "sí"}


def _set_formset_notas_queryset(formset, cliente):
    notas = NotaVenta.objects.filter(cliente_ref=cliente, estado=NotaVenta.ESTADO_ACTIVA).order_by("-fecha", "-folio")
    for form in formset.forms:
        form.fields["nota_id"].queryset = notas
        form.fields["nota_id"].label_from_instance = lambda nota: f"{nota.folio} · {nota.fecha:%Y-%m-%d}"


def _aplicaciones_desde_formset(formset):
    aplicaciones = []
    for form in formset.forms:
        if not form.cleaned_data:
            continue
        nota = form.cleaned_data.get("nota_id")
        monto = form.cleaned_data.get("monto")
        if nota and monto:
            aplicaciones.append({
                "nota_id": nota.pk,
                "monto": monto,
                "observaciones": form.cleaned_data.get("observaciones", ""),
            })
    return aplicaciones


@permiso_requerido("cartera.add_pagocliente")
def pago_global_create(request):
    if not _puede_registrar_pagos(request.user):
        messages.error(request, "No tienes permiso para registrar pagos.")
        return redirect("cartera:dashboard")

    cliente_id = request.POST.get("cliente") or request.GET.get("cliente")
    busqueda_cliente = (request.GET.get("cliente_q") or "").strip()
    cliente_seleccionado = None
    clientes_encontrados = []
    notas_pendientes = []
    total_adeudado = Decimal("0.00")
    saldo_favor = Decimal("0.00")

    if cliente_id:
        cliente_seleccionado = get_object_or_404(Cliente, pk=cliente_id, activo=True)
        notas_pendientes = list(get_notas_con_saldo_pendiente(cliente_seleccionado))
        total_adeudado = get_total_adeudado_cliente(cliente_seleccionado)
        saldo_favor = get_saldo_favor_cliente(cliente_seleccionado)
    elif busqueda_cliente:
        clientes_encontrados = list(_buscar_clientes(busqueda_cliente))

    if request.method == "POST":
        form = PagoGlobalForm(request.POST)
        if form.is_valid():
            cliente = form.cleaned_data["cliente"]
            monto = form.cleaned_data["monto"]
            metodo = form.cleaned_data["metodo"]
            referencia = form.cleaned_data["referencia"]
            observaciones = form.cleaned_data["observaciones"]
            try:
                pago = registrar_pago_fifo(
                    cliente=cliente,
                    monto_recibido=monto,
                    metodos=[{"metodo": metodo, "monto": monto, "referencia": referencia}],
                    usuario=request.user,
                    referencia=referencia,
                    observaciones=observaciones,
                    fecha_pago=form.cleaned_data["fecha_pago"],
                )
            except ValidationError as exc:
                form.add_error(None, exc)
            else:
                total_aplicado = pago.aplicaciones.aggregate(total=Sum("monto_aplicado"))["total"] or Decimal("0.00")
                saldo_generado = (
                    ClienteSaldoFavorMovimiento.objects.filter(
                        pago_origen=pago,
                        tipo=ClienteSaldoFavorMovimiento.TIPO_GENERACION,
                    ).aggregate(total=Sum("monto"))["total"]
                    or Decimal("0.00")
                )
                mensaje = f"Pago registrado correctamente. Aplicado a notas: ${total_aplicado:,.2f}."
                if saldo_generado > 0:
                    mensaje += f" Saldo a favor generado: ${saldo_generado:,.2f}."
                messages.success(request, mensaje)
                return redirect("cartera:pago_detalle", pago_id=pago.id)
    else:
        form = PagoGlobalForm(initial={"cliente": cliente_id})

    return render(
        request,
        "cartera/pago_global_form.html",
        {
            "form": form,
            "busqueda_cliente": busqueda_cliente,
            "clientes_encontrados": clientes_encontrados,
            "cliente_seleccionado": cliente_seleccionado,
            "notas_pendientes": notas_pendientes,
            "total_adeudado": total_adeudado,
            "saldo_favor": saldo_favor,
        },
    )


@permiso_requerido("cartera.add_pagocliente")
def pago_nota_create(request, nota_id):
    if not _puede_registrar_pagos(request.user):
        messages.error(request, "No tienes permiso para registrar pagos.")
        return redirect("cartera:dashboard")

    nota = get_object_or_404(
        NotaVenta.objects.select_related("cliente_ref"),
        pk=nota_id,        estado=NotaVenta.ESTADO_ACTIVA,
    )
    if not nota.cliente_ref_id:
        messages.error(request, "La nota no tiene cliente de catálogo asignado.")
        return redirect("cartera:dashboard")

    saldo = get_saldo_pendiente_nota(nota)
    total = get_total_nota(nota)
    if request.method == "POST":
        form = PagoNotaForm(request.POST)
        if form.is_valid():
            monto = form.cleaned_data["monto"]
            try:
                pago = registrar_pago_notas_especificas(
                    cliente=nota.cliente_ref,
                    monto_recibido=monto,
                    aplicaciones=[{"nota_id": nota.id, "monto": monto}],
                    metodos=[{"metodo": form.cleaned_data["metodo"], "monto": monto, "referencia": form.cleaned_data["referencia"]}],
                    usuario=request.user,
                    referencia=form.cleaned_data["referencia"],
                    observaciones=form.cleaned_data["observaciones"],
                    fecha_pago=form.cleaned_data["fecha_pago"],
                )
            except ValidationError as exc:
                form.add_error(None, exc)
            else:
                messages.success(request, f"Pago aplicado correctamente a la nota {nota.folio}.")
                return redirect("cartera:pago_detalle", pago_id=pago.id)
    else:
        form = PagoNotaForm(initial={"monto": saldo})

    aplicaciones = PagoAplicacionNota.objects.filter(nota_venta=nota, pago__estado=PagoCliente.ESTADO_ACTIVO).select_related("pago", "creado_por").order_by("-aplicado_en")

    return render(
        request,
        "cartera/pago_nota_form.html",
        {"form": form, "nota": nota, "total_nota": total, "saldo_pendiente": saldo, "aplicaciones": aplicaciones},
    )


@permiso_requerido("cartera.view_pagocliente")
def pago_detalle(request, pago_id):
    pago = get_object_or_404(
        PagoCliente.objects.select_related("cliente", "creado_por")
        .prefetch_related("metodos", "aplicaciones__nota_venta", "aplicaciones__creado_por", "movimientos_saldo_favor"),
        pk=pago_id,
    )
    total_aplicado = pago.aplicaciones.aggregate(total=Sum("monto_aplicado"))["total"] or Decimal("0.00")
    saldo_generado = (
        pago.movimientos_saldo_favor.filter(tipo=ClienteSaldoFavorMovimiento.TIPO_GENERACION).aggregate(total=Sum("monto"))["total"]
        or Decimal("0.00")
    )
    saldo_reversado = (
        pago.movimientos_saldo_favor.filter(tipo=ClienteSaldoFavorMovimiento.TIPO_CANCELACION).aggregate(total=Sum("monto"))["total"]
        or Decimal("0.00")
    )
    notas_pendientes = list(get_notas_con_saldo_pendiente(pago.cliente))

    return render(
        request,
        "cartera/pago_detalle.html",
        {
            "pago": pago,
            "total_aplicado": total_aplicado,
            "saldo_generado": saldo_generado,
            "saldo_reversado": saldo_reversado,
            "notas_pendientes": notas_pendientes,
            "cancelar_form": CancelarPagoForm(),
            "puede_cancelar_pagos": _puede_cancelar_pagos(request.user),
        },
    )


@permiso_requerido("cartera.puede_cancelar_pagos", "cartera.change_pagocliente")
@require_POST
def pago_cancelar(request, pago_id):
    if not _puede_cancelar_pagos(request.user):
        messages.error(request, "No tienes permiso para cancelar pagos.")
        return redirect("cartera:pago_detalle", pago_id=pago_id)

    pago = get_object_or_404(PagoCliente.objects.select_related("cliente"), pk=pago_id)
    form = CancelarPagoForm(request.POST)
    if not form.is_valid():
        errores = []
        for campo_errores in form.errors.values():
            errores.extend(campo_errores)
        messages.error(request, " ".join(errores) or "No se pudo cancelar el pago.")
        return redirect("cartera:pago_detalle", pago_id=pago.id)

    try:
        cancelar_pago_cliente(
            pago=pago,
            usuario=request.user,
            motivo=form.cleaned_data["motivo_cancelacion"],
        )
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages) if hasattr(exc, "messages") else str(exc))
    else:
        messages.success(request, f"Pago #{pago.id} cancelado correctamente. Las notas afectadas fueron recalculadas.")

    return redirect("cartera:pago_detalle", pago_id=pago.id)


@permiso_requerido("cartera.view_pagocliente")
def pago_detalle_print(request, pago_id):
    pago = get_object_or_404(
        PagoCliente.objects.select_related("cliente")
        .prefetch_related("metodos", "aplicaciones__nota_venta", "movimientos_saldo_favor"),
        pk=pago_id,
    )
    total_aplicado = pago.aplicaciones.aggregate(total=Sum("monto_aplicado"))["total"] or Decimal("0.00")
    saldo_generado = (
        pago.movimientos_saldo_favor.filter(tipo=ClienteSaldoFavorMovimiento.TIPO_GENERACION).aggregate(total=Sum("monto"))["total"]
        or Decimal("0.00")
    )
    saldo_reversado = (
        pago.movimientos_saldo_favor.filter(tipo=ClienteSaldoFavorMovimiento.TIPO_CANCELACION).aggregate(total=Sum("monto"))["total"]
        or Decimal("0.00")
    )
    notas_pendientes = list(get_notas_con_saldo_pendiente(pago.cliente))
    return render(request, "cartera/prints/pago_detalle_print.html", {"pago": pago, "total_aplicado": total_aplicado, "saldo_generado": saldo_generado, "saldo_reversado": saldo_reversado, "notas_pendientes": notas_pendientes, "empresa": _empresa_contexto(), "emitido_en": timezone.now()})


@permiso_requerido("cartera.view_pagocliente", "ventas.view_notaventa", "inventarios.view_salidainventario")
def estado_cuenta_cliente(request, cliente_id):
    cliente = get_object_or_404(Cliente, pk=cliente_id, activo=True)
    estado = get_estado_cuenta_cliente(cliente)
    incluir_facturacion = _facturacion_activa(request) and _puede_ver_facturacion(request.user)
    if incluir_facturacion:
        estado["facturacion"] = get_estado_facturacion_cliente(cliente)
    movimientos_opcion, movimientos_limite = _get_movimientos_limit(request)

    pagos_qs = estado["pagos"]
    movimientos_saldo_qs = ClienteSaldoFavorMovimiento.objects.filter(cliente=cliente).select_related("creado_por", "autorizado_por", "pago_origen", "nota_aplicada").order_by("-fecha", "-id")

    total_pagos = pagos_qs.count()
    total_movimientos_saldo = movimientos_saldo_qs.count()

    if movimientos_limite is not None:
        estado["pagos"] = pagos_qs[:movimientos_limite]
        movimientos_saldo = movimientos_saldo_qs[:movimientos_limite]
    else:
        movimientos_saldo = movimientos_saldo_qs

    return render(
        request,
        "cartera/estado_cuenta_cliente.html",
        {
            "estado": estado,
            "cliente": cliente,
            "movimientos_saldo": movimientos_saldo,
            "movimientos_opcion": movimientos_opcion,
            "total_pagos": total_pagos,
            "total_movimientos_saldo": total_movimientos_saldo,
            "incluir_facturacion": incluir_facturacion,
            "puede_ver_facturacion": _puede_ver_facturacion(request.user),
            "puede_registrar_facturas": _puede_registrar_facturas(request.user),
            "puede_cancelar_pagos": _puede_cancelar_pagos(request.user),
        },
    )


@permiso_requerido("cartera.view_pagocliente", "ventas.view_notaventa", "inventarios.view_salidainventario")
def estado_cuenta_cliente_print(request, cliente_id):
    cliente = get_object_or_404(Cliente, pk=cliente_id, activo=True)
    estado = get_estado_cuenta_cliente(cliente)
    incluir_facturacion = _facturacion_activa(request) and _puede_ver_facturacion(request.user)
    if incluir_facturacion:
        estado["facturacion"] = get_estado_facturacion_cliente(cliente)
    movimientos_opcion, movimientos_limite = _get_movimientos_limit(request)
    movimientos_saldo_qs = ClienteSaldoFavorMovimiento.objects.filter(cliente=cliente).select_related("pago_origen", "nota_aplicada").order_by("-fecha", "-id")

    if movimientos_limite is not None:
        estado["pagos"] = estado["pagos"][:movimientos_limite]
        movimientos_saldo = movimientos_saldo_qs[:movimientos_limite]
    else:
        movimientos_saldo = movimientos_saldo_qs

    return render(request, "cartera/prints/estado_cuenta_cliente_print.html", {"estado": estado, "cliente": cliente, "movimientos_saldo": movimientos_saldo, "empresa": _empresa_contexto(), "emitido_en": timezone.now(), "movimientos_opcion": movimientos_opcion, "incluir_facturacion": incluir_facturacion})


@permiso_requerido("cartera.view_pagocliente", "ventas.view_notaventa", "inventarios.view_salidainventario")
def reporte_cartera_general(request):
    query = (request.GET.get("q") or "").strip()
    estado_query = (request.GET.get("estado_q") or "").strip()
    clientes_estado_encontrados = list(_buscar_clientes(estado_query, limit=20)) if estado_query else []

    clientes = Cliente.objects.filter(activo=True).order_by("nombre_fiscal", "nombre_comercial")
    if query:
        clientes = clientes.filter(Q(nombre_fiscal__icontains=query) | Q(nombre_comercial__icontains=query) | Q(rfc__icontains=query))

    filas = []
    total_general = Decimal("0.00")
    saldo_favor_general = Decimal("0.00")
    for cliente in clientes[:300]:
        notas = list(get_notas_con_saldo_pendiente(cliente))
        adeudo = sum((n.saldo_pendiente for n in notas), Decimal("0.00"))
        saldo_favor = get_saldo_favor_cliente(cliente)
        if adeudo > 0 or saldo_favor > 0 or query:
            filas.append({"cliente": cliente, "notas": len(notas), "adeudo": adeudo, "saldo_favor": saldo_favor})
            total_general += adeudo
            saldo_favor_general += saldo_favor

    return render(request, "cartera/reporte_cartera_general.html", {"query": query, "filas": filas, "total_general": total_general, "saldo_favor_general": saldo_favor_general})


@permiso_requerido("cartera.view_pagocliente", "ventas.view_notaventa", "inventarios.view_salidainventario")
def reporte_cartera_general_print(request):
    query = (request.GET.get("q") or "").strip()
    estado_query = (request.GET.get("estado_q") or "").strip()
    clientes_estado_encontrados = list(_buscar_clientes(estado_query, limit=20)) if estado_query else []

    clientes = Cliente.objects.filter(activo=True).order_by("nombre_fiscal", "nombre_comercial")
    if query:
        clientes = clientes.filter(Q(nombre_fiscal__icontains=query) | Q(nombre_comercial__icontains=query) | Q(rfc__icontains=query))

    filas = []
    total_general = Decimal("0.00")
    saldo_favor_general = Decimal("0.00")
    for cliente in clientes[:300]:
        notas = list(get_notas_con_saldo_pendiente(cliente))
        adeudo = sum((n.saldo_pendiente for n in notas), Decimal("0.00"))
        saldo_favor = get_saldo_favor_cliente(cliente)
        if adeudo > 0 or saldo_favor > 0 or query:
            filas.append({"cliente": cliente, "notas": len(notas), "adeudo": adeudo, "saldo_favor": saldo_favor})
            total_general += adeudo
            saldo_favor_general += saldo_favor
    return render(request, "cartera/prints/reporte_cartera_general_print.html", {"query": query, "filas": filas, "total_general": total_general, "saldo_favor_general": saldo_favor_general, "empresa": _empresa_contexto(), "emitido_en": timezone.now()})


@permiso_requerido("cartera.view_pagocliente")
def reporte_pagos_dia(request):
    fecha_txt = request.GET.get("fecha") or timezone.localdate().isoformat()
    try:
        fecha = date.fromisoformat(fecha_txt)
    except ValueError:
        fecha = timezone.localdate()

    cantidad, cantidad_limite, cantidad_opciones = _get_cantidad_reporte(request)
    pagos_qs = PagoCliente.objects.filter(fecha__date=fecha).select_related("cliente", "creado_por").prefetch_related("aplicaciones__nota_venta", "metodos").order_by("-fecha", "-id")
    total_recibido = pagos_qs.filter(estado=PagoCliente.ESTADO_ACTIVO).aggregate(total=Sum("monto_recibido"))["total"] or Decimal("0.00")
    total_registros = pagos_qs.count()
    pagos = pagos_qs if cantidad_limite is None else pagos_qs[:cantidad_limite]
    total_mostrado = total_registros if cantidad_limite is None else min(cantidad_limite, total_registros)

    return render(
        request,
        "cartera/reporte_pagos_dia.html",
        {
            "fecha": fecha,
            "pagos": pagos,
            "total_recibido": total_recibido,
            "cantidad": cantidad,
            "cantidad_opciones": cantidad_opciones,
            "total_mostrado": total_mostrado,
            "total_registros": total_registros,
        },
    )


@permiso_requerido("cartera.view_pagocliente")
def reporte_pagos_dia_print(request):
    fecha_txt = request.GET.get("fecha") or timezone.localdate().isoformat()
    try:
        fecha = date.fromisoformat(fecha_txt)
    except ValueError:
        fecha = timezone.localdate()

    cantidad, cantidad_limite, _cantidad_opciones = _get_cantidad_reporte(request)
    pagos_qs = PagoCliente.objects.filter(fecha__date=fecha).select_related("cliente").prefetch_related("aplicaciones__nota_venta", "metodos").order_by("fecha", "id")
    total_recibido = pagos_qs.filter(estado=PagoCliente.ESTADO_ACTIVO).aggregate(total=Sum("monto_recibido"))["total"] or Decimal("0.00")
    total_registros = pagos_qs.count()
    pagos = pagos_qs if cantidad_limite is None else pagos_qs[:cantidad_limite]
    total_mostrado = total_registros if cantidad_limite is None else min(cantidad_limite, total_registros)
    return render(request, "cartera/prints/reporte_pagos_dia_print.html", {"fecha": fecha, "pagos": pagos, "total_recibido": total_recibido, "cantidad": cantidad, "total_mostrado": total_mostrado, "total_registros": total_registros, "empresa": _empresa_contexto(), "emitido_en": timezone.now()})


@permiso_requerido("cartera.add_pagoaplicacionnota", "cartera.change_clientesaldofavormovimiento")
def aplicar_saldo_favor(request, cliente_id):
    if not _puede_registrar_pagos(request.user):
        messages.error(request, "No tienes permiso para aplicar saldo a favor.")
        return redirect("cartera:dashboard")

    cliente = get_object_or_404(Cliente, pk=cliente_id, activo=True)
    saldo_favor = get_saldo_favor_cliente(cliente)
    notas_pendientes = list(get_notas_con_saldo_pendiente(cliente))
    movimientos = (
        ClienteSaldoFavorMovimiento.objects.filter(cliente=cliente)
        .select_related("creado_por", "autorizado_por", "pago_origen", "nota_aplicada")
        .order_by("-fecha", "-id")[:25]
    )

    nota_seleccionada = None
    nota_saldo_pendiente = Decimal("0.00")

    nota_id = request.POST.get("nota_id") or request.GET.get("nota")
    if nota_id:
        nota_seleccionada = get_object_or_404(
            NotaVenta.objects.select_related("cliente_ref"),
            pk=nota_id,
            cliente_ref=cliente,            estado=NotaVenta.ESTADO_ACTIVA,
        )
        nota_saldo_pendiente = get_saldo_pendiente_nota(nota_seleccionada)

    if request.method == "POST":
        form = SaldoFavorAplicacionForm(request.POST)
        if form.is_valid():
            nota = get_object_or_404(
                NotaVenta.objects.select_related("cliente_ref"),
                pk=form.cleaned_data["nota_id"],
                cliente_ref=cliente,                estado=NotaVenta.ESTADO_ACTIVA,
            )
            try:
                aplicar_saldo_favor_a_nota(
                    cliente=cliente,
                    nota=nota,
                    monto=form.cleaned_data["monto"],
                    usuario=request.user,
                    referencia=form.cleaned_data["referencia"],
                    observaciones=form.cleaned_data["observaciones"],
                    fecha_aplicacion=form.cleaned_data["fecha_pago"],
                )
            except ValidationError as exc:
                form.add_error(None, exc)
                nota_seleccionada = nota
                nota_saldo_pendiente = get_saldo_pendiente_nota(nota)
            else:
                messages.success(request, f"Saldo a favor aplicado correctamente a la nota {nota.folio}.")
                return redirect("cartera:estado_cuenta_cliente", cliente_id=cliente.id)
    else:
        initial = {}
        if nota_seleccionada:
            initial = {
                "nota_id": nota_seleccionada.id,
                "monto": min(saldo_favor, nota_saldo_pendiente),
            }
        form = SaldoFavorAplicacionForm(initial=initial)

    return render(
        request,
        "cartera/aplicar_saldo_favor.html",
        {
            "cliente": cliente,
            "saldo_favor": saldo_favor,
            "notas_pendientes": notas_pendientes,
            "nota_seleccionada": nota_seleccionada,
            "nota_saldo_pendiente": nota_saldo_pendiente,
            "form": form,
            "movimientos": movimientos,
        },
    )


@permiso_requerido("cartera.add_clientesaldofavormovimiento", "cartera.change_clientesaldofavormovimiento")
def liquidar_saldo_favor(request, cliente_id):
    if not _puede_registrar_pagos(request.user):
        messages.error(request, "No tienes permiso para liquidar saldo a favor.")
        return redirect("cartera:dashboard")
    cliente = get_object_or_404(Cliente, pk=cliente_id, activo=True)
    saldo_favor = get_saldo_favor_cliente(cliente)
    movimientos = ClienteSaldoFavorMovimiento.objects.filter(cliente=cliente).select_related("creado_por", "autorizado_por", "pago_origen").order_by("-fecha", "-id")[:25]

    if request.method == "POST":
        form = SaldoFavorDevolucionForm(request.POST)
        if form.is_valid():
            try:
                devolver_saldo_favor(
                    cliente=cliente,
                    monto=form.cleaned_data["monto"],
                    metodo=form.cleaned_data["metodo"],
                    usuario_autoriza=request.user,
                    usuario_registra=request.user,
                    referencia=form.cleaned_data["referencia"],
                    observaciones=form.cleaned_data["observaciones"],
                    fecha_liquidacion=form.cleaned_data["fecha_liquidacion"],
                )
            except ValidationError as exc:
                form.add_error(None, exc)
            else:
                messages.success(request, "Saldo a favor liquidado correctamente con trazabilidad de usuario, fecha y referencia.")
                return redirect("cartera:estado_cuenta_cliente", cliente_id=cliente.id)
    else:
        form = SaldoFavorDevolucionForm(initial={"monto": saldo_favor})

    return render(request, "cartera/liquidar_saldo_favor.html", {"cliente": cliente, "saldo_favor": saldo_favor, "form": form, "movimientos": movimientos})

@permiso_requerido("cartera.view_facturacliente", "cartera.puede_ver_facturacion")
def factura_list(request):
    if not _puede_ver_facturacion(request.user):
        messages.error(request, "No tienes permiso para ver facturación.")
        return redirect("cartera:dashboard")
    form = ReporteFacturacionForm(request.GET or None)
    facturas = get_reporte_facturacion_por_cliente()
    if form.is_valid():
        facturas = get_reporte_facturacion_por_cliente(
            fecha_inicio=form.cleaned_data.get("fecha_inicio"),
            fecha_fin=form.cleaned_data.get("fecha_fin"),
            cliente_query=form.cleaned_data.get("q", ""),
            estado=form.cleaned_data.get("estado", ""),
            tipo_aplicacion=form.cleaned_data.get("tipo_aplicacion", ""),
        )
    resumen = get_reporte_facturacion_resumen(facturas)
    resumen_clientes = get_reporte_facturacion_resumen_clientes(facturas)
    return render(request, "cartera/facturacion/factura_list.html", {"form": form, "facturas": facturas[:300], "resumen": resumen, "resumen_clientes": resumen_clientes, "puede_registrar_facturas": _puede_registrar_facturas(request.user)})


def _factura_create_context(request, nota=None):
    cliente_id = request.POST.get("cliente") or request.GET.get("cliente") or (nota.cliente_ref_id if nota else None)
    busqueda_cliente = (request.GET.get("cliente_q") or "").strip()
    cliente = get_object_or_404(Cliente, pk=cliente_id, activo=True) if cliente_id else None
    clientes_encontrados = list(_buscar_clientes(busqueda_cliente)) if busqueda_cliente and not cliente else []
    form_initial = {"cliente": cliente.pk} if cliente else {}
    if nota:
        form_initial["tipo_aplicacion"] = FacturaCliente.TIPO_NOTAS
    form = FacturaClienteForm(request.POST or None, request.FILES or None, initial=form_initial)
    formset_initial = []
    if nota:
        formset_initial.append({"nota_id": nota.pk})
    formset = FacturaAplicacionNotaFormSet(request.POST or None, initial=formset_initial, prefix="aplicaciones")
    if cliente:
        _set_formset_notas_queryset(formset, cliente)
    return cliente, clientes_encontrados, busqueda_cliente, form, formset


@permiso_requerido("cartera.add_facturacliente", "cartera.puede_registrar_facturas")
def factura_create(request):
    if not _puede_registrar_facturas(request.user):
        messages.error(request, "No tienes permiso para registrar facturas.")
        return redirect("cartera:dashboard")
    cliente, clientes_encontrados, busqueda_cliente, form, formset = _factura_create_context(request)
    if request.method == "POST" and form.is_valid() and formset.is_valid():
        try:
            factura = registrar_factura_cliente(
                cliente=form.cleaned_data["cliente"],
                xml_file=form.cleaned_data["xml"],
                monto=form.cleaned_data["monto"],
                tipo_aplicacion=form.cleaned_data["tipo_aplicacion"],
                aplicaciones=_aplicaciones_desde_formset(formset),
                usuario=request.user,
                referencia=form.cleaned_data["referencia"],
                observaciones=form.cleaned_data["observaciones"],
            )
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, f"Factura {factura.folio_display} registrada para control interno.")
            return redirect("cartera:factura_detalle", factura_id=factura.id)
    return render(request, "cartera/facturacion/factura_form.html", {"form": form, "formset": formset, "cliente_seleccionado": cliente, "clientes_encontrados": clientes_encontrados, "busqueda_cliente": busqueda_cliente})


@permiso_requerido("cartera.add_facturacliente", "cartera.puede_registrar_facturas")
def factura_create_desde_nota(request, nota_id):
    nota = get_object_or_404(NotaVenta.objects.select_related("cliente_ref"), pk=nota_id, estado=NotaVenta.ESTADO_ACTIVA)
    if not nota.cliente_ref_id:
        messages.error(request, "La nota no tiene cliente de catálogo asignado.")
        return redirect("cartera:dashboard")
    cliente, clientes_encontrados, busqueda_cliente, form, formset = _factura_create_context(request, nota=nota)
    if request.method == "POST" and form.is_valid() and formset.is_valid():
        try:
            factura = registrar_factura_cliente(
                cliente=form.cleaned_data["cliente"],
                xml_file=form.cleaned_data["xml"],
                monto=form.cleaned_data["monto"],
                tipo_aplicacion=form.cleaned_data["tipo_aplicacion"],
                aplicaciones=_aplicaciones_desde_formset(formset),
                usuario=request.user,
                referencia=form.cleaned_data["referencia"],
                observaciones=form.cleaned_data["observaciones"],
            )
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, f"Factura {factura.folio_display} registrada desde la nota {nota.folio}.")
            return redirect("cartera:factura_detalle", factura_id=factura.id)
    return render(request, "cartera/facturacion/factura_form.html", {"form": form, "formset": formset, "cliente_seleccionado": cliente, "clientes_encontrados": clientes_encontrados, "busqueda_cliente": busqueda_cliente, "nota_origen": nota})


@permiso_requerido("cartera.view_facturacliente", "cartera.puede_ver_facturacion")
def factura_detalle(request, factura_id):
    factura = get_object_or_404(FacturaCliente.objects.select_related("cliente", "creado_por", "cancelado_por").prefetch_related("aplicaciones__nota_venta"), pk=factura_id)
    return render(request, "cartera/facturacion/factura_detalle.html", {"factura": factura, "cancelar_form": CancelarFacturaForm(), "puede_cancelar_facturas": _puede_cancelar_facturas(request.user)})


@permiso_requerido("cartera.view_facturacliente", "cartera.puede_ver_facturacion")
def factura_xml_download(request, factura_id):
    factura = get_object_or_404(FacturaCliente, pk=factura_id)
    if not factura.xml:
        raise Http404("XML no disponible")
    filename = f"{factura.uuid}.xml"
    return FileResponse(factura.xml.open("rb"), as_attachment=True, filename=filename, content_type="application/xml")


@permiso_requerido("cartera.view_facturacliente", "cartera.puede_ver_facturacion")
def factura_preview_print(request, factura_id):
    factura = get_object_or_404(FacturaCliente.objects.select_related("cliente").prefetch_related("aplicaciones__nota_venta"), pk=factura_id)
    return render(
        request,
        "cartera/prints/factura_preview_print.html",
        {
            "factura": factura,
            "xml_pretty": pretty_xml_factura(factura),
            "empresa": _empresa_contexto(),
            "emitido_en": timezone.now(),
        },
    )


@permiso_requerido("cartera.puede_cancelar_facturas", "cartera.change_facturacliente")
@require_POST
def factura_cancelar(request, factura_id):
    factura = get_object_or_404(FacturaCliente, pk=factura_id)
    if not _puede_cancelar_facturas(request.user):
        messages.error(request, "No tienes permiso para cancelar facturas.")
        return redirect("cartera:factura_detalle", factura_id=factura.id)
    form = CancelarFacturaForm(request.POST)
    if form.is_valid():
        try:
            cancelar_factura_cliente(factura, request.user, form.cleaned_data["motivo_cancelacion"])
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages) if hasattr(exc, "messages") else str(exc))
        else:
            messages.success(request, "Factura cancelada internamente. El XML y sus aplicaciones se conservaron.")
    else:
        messages.error(request, " ".join(error for errors in form.errors.values() for error in errors))
    return redirect("cartera:factura_detalle", factura_id=factura.id)


@permiso_requerido("cartera.view_facturacliente", "cartera.puede_ver_facturacion")
def facturacion_cliente_reporte(request, cliente_id):
    cliente = get_object_or_404(Cliente, pk=cliente_id, activo=True)
    facturas = get_facturas_cliente(cliente, incluir_canceladas=True)
    resumen = get_facturacion_cliente_resumen(cliente)
    return render(request, "cartera/facturacion/facturacion_cliente_reporte.html", {"cliente": cliente, "facturas": facturas, "resumen": resumen})


@permiso_requerido("cartera.view_facturacliente", "cartera.puede_ver_facturacion")
def facturacion_cliente_reporte_print(request, cliente_id):
    cliente = get_object_or_404(Cliente, pk=cliente_id, activo=True)
    facturas = get_facturas_cliente(cliente, incluir_canceladas=True)
    resumen = get_facturacion_cliente_resumen(cliente)
    return render(
        request,
        "cartera/prints/facturacion_cliente_reporte_print.html",
        {
            "cliente": cliente,
            "facturas": facturas,
            "resumen": resumen,
            "empresa": _empresa_contexto(),
            "emitido_en": timezone.now(),
        },
    )


@permiso_requerido("cartera.view_facturacliente", "cartera.puede_ver_facturacion")
def reporte_facturacion_clientes(request):
    form = ReporteFacturacionForm(request.GET or None)
    facturas = get_reporte_facturacion_por_cliente()
    if form.is_valid():
        facturas = get_reporte_facturacion_por_cliente(
            fecha_inicio=form.cleaned_data.get("fecha_inicio"),
            fecha_fin=form.cleaned_data.get("fecha_fin"),
            cliente_query=form.cleaned_data.get("q", ""),
            estado=form.cleaned_data.get("estado", ""),
            tipo_aplicacion=form.cleaned_data.get("tipo_aplicacion", ""),
        )
    resumen = get_reporte_facturacion_resumen(facturas)
    resumen_clientes = get_reporte_facturacion_resumen_clientes(facturas)
    return render(request, "cartera/facturacion/reporte_facturacion_clientes.html", {"form": form, "facturas": facturas[:500], "resumen": resumen, "resumen_clientes": resumen_clientes})


@permiso_requerido("cartera.view_facturacliente", "cartera.puede_ver_facturacion")
def reporte_facturacion_clientes_print(request):
    form = ReporteFacturacionForm(request.GET or None)
    facturas = get_reporte_facturacion_por_cliente()
    if form.is_valid():
        facturas = get_reporte_facturacion_por_cliente(
            fecha_inicio=form.cleaned_data.get("fecha_inicio"),
            fecha_fin=form.cleaned_data.get("fecha_fin"),
            cliente_query=form.cleaned_data.get("q", ""),
            estado=form.cleaned_data.get("estado", ""),
            tipo_aplicacion=form.cleaned_data.get("tipo_aplicacion", ""),
        )
    resumen = get_reporte_facturacion_resumen(facturas)
    resumen_clientes = get_reporte_facturacion_resumen_clientes(facturas)
    return render(request, "cartera/prints/reporte_facturacion_clientes_print.html", {"facturas": facturas[:500], "resumen": resumen, "resumen_clientes": resumen_clientes, "empresa": _empresa_contexto(), "emitido_en": timezone.now()})

