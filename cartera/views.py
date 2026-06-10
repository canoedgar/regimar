from datetime import date
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from catalogos.models import Cliente, ParametroSistema
from inventarios.models import SalidaInventario
from cartera.forms import PagoGlobalForm, PagoNotaForm, SaldoFavorAplicacionForm, SaldoFavorDevolucionForm
from cartera.models import ClienteSaldoFavorMovimiento, PagoAplicacionNota, PagoCliente
from cartera.selectors.cartera import (
    get_estado_cuenta_cliente,
    get_notas_con_saldo_pendiente,
    get_saldo_favor_cliente,
    get_saldo_pendiente_nota,
    get_total_adeudado_cliente,
    get_total_nota,
)
from cartera.services.cartera import aplicar_saldo_favor_a_nota, devolver_saldo_favor, registrar_pago_fifo, registrar_pago_notas_especificas


def _puede_registrar_pagos(user):
    return (
        user.is_superuser
        or user.has_perm("cartera.puede_registrar_pagos")
        or user.groups.filter(name__in=["Ventas", "Administrador"]).exists()
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


def _empresa_contexto():
    return {
        "nombre": ParametroSistema.objects.filter(clave="EMPRESA_NOMBRE", activo=True).values_list("valor", flat=True).first() or "CPC Alimentos",
        "propietario": ParametroSistema.objects.filter(clave="EMPRESA_PROPIETARIO", activo=True).values_list("valor", flat=True).first() or "Jaime Parada Villarreal",
        "direccion": ParametroSistema.objects.filter(clave="EMPRESA_DIRECCION", activo=True).values_list("valor", flat=True).first() or "Mexicali, B.C. CP. 21376",
        "telefono": ParametroSistema.objects.filter(clave="EMPRESA_TELEFONO", activo=True).values_list("valor", flat=True).first() or "686 162 7239",
        "email": ParametroSistema.objects.filter(clave="EMPRESA_EMAIL", activo=True).values_list("valor", flat=True).first() or "cpcalimentosbc@gmail.com",
    }


@login_required
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
        },
    )


@login_required
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


@login_required
def pago_nota_create(request, nota_id):
    if not _puede_registrar_pagos(request.user):
        messages.error(request, "No tienes permiso para registrar pagos.")
        return redirect("cartera:dashboard")

    nota = get_object_or_404(
        SalidaInventario.objects.select_related("cliente_ref"),
        pk=nota_id,
        tipo=SalidaInventario.TIPO_VENTA,
        estado=SalidaInventario.ESTADO_ACTIVA,
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


@login_required
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
    notas_pendientes = list(get_notas_con_saldo_pendiente(pago.cliente))

    return render(
        request,
        "cartera/pago_detalle.html",
        {"pago": pago, "total_aplicado": total_aplicado, "saldo_generado": saldo_generado, "notas_pendientes": notas_pendientes},
    )


@login_required
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
    notas_pendientes = list(get_notas_con_saldo_pendiente(pago.cliente))
    return render(request, "cartera/prints/pago_detalle_print.html", {"pago": pago, "total_aplicado": total_aplicado, "saldo_generado": saldo_generado, "notas_pendientes": notas_pendientes, "empresa": _empresa_contexto(), "emitido_en": timezone.now()})


@login_required
def estado_cuenta_cliente(request, cliente_id):
    cliente = get_object_or_404(Cliente, pk=cliente_id, activo=True)
    estado = get_estado_cuenta_cliente(cliente)
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
        },
    )


@login_required
def estado_cuenta_cliente_print(request, cliente_id):
    cliente = get_object_or_404(Cliente, pk=cliente_id, activo=True)
    estado = get_estado_cuenta_cliente(cliente)
    movimientos_opcion, movimientos_limite = _get_movimientos_limit(request)
    movimientos_saldo_qs = ClienteSaldoFavorMovimiento.objects.filter(cliente=cliente).select_related("pago_origen", "nota_aplicada").order_by("-fecha", "-id")

    if movimientos_limite is not None:
        estado["pagos"] = estado["pagos"][:movimientos_limite]
        movimientos_saldo = movimientos_saldo_qs[:movimientos_limite]
    else:
        movimientos_saldo = movimientos_saldo_qs

    return render(request, "cartera/prints/estado_cuenta_cliente_print.html", {"estado": estado, "cliente": cliente, "movimientos_saldo": movimientos_saldo, "empresa": _empresa_contexto(), "emitido_en": timezone.now(), "movimientos_opcion": movimientos_opcion})


@login_required
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


@login_required
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


@login_required
def reporte_pagos_dia(request):
    fecha_txt = request.GET.get("fecha") or timezone.localdate().isoformat()
    try:
        fecha = date.fromisoformat(fecha_txt)
    except ValueError:
        fecha = timezone.localdate()
    pagos = PagoCliente.objects.filter(fecha__date=fecha).select_related("cliente", "creado_por").prefetch_related("aplicaciones__nota_venta", "metodos").order_by("-fecha", "-id")
    total_recibido = pagos.filter(estado=PagoCliente.ESTADO_ACTIVO).aggregate(total=Sum("monto_recibido"))["total"] or Decimal("0.00")
    return render(request, "cartera/reporte_pagos_dia.html", {"fecha": fecha, "pagos": pagos, "total_recibido": total_recibido})


@login_required
def reporte_pagos_dia_print(request):
    fecha_txt = request.GET.get("fecha") or timezone.localdate().isoformat()
    try:
        fecha = date.fromisoformat(fecha_txt)
    except ValueError:
        fecha = timezone.localdate()
    pagos = PagoCliente.objects.filter(fecha__date=fecha).select_related("cliente").prefetch_related("aplicaciones__nota_venta", "metodos").order_by("fecha", "id")
    total_recibido = pagos.filter(estado=PagoCliente.ESTADO_ACTIVO).aggregate(total=Sum("monto_recibido"))["total"] or Decimal("0.00")
    return render(request, "cartera/prints/reporte_pagos_dia_print.html", {"fecha": fecha, "pagos": pagos, "total_recibido": total_recibido, "empresa": _empresa_contexto(), "emitido_en": timezone.now()})


@login_required
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
            SalidaInventario.objects.select_related("cliente_ref"),
            pk=nota_id,
            cliente_ref=cliente,
            tipo=SalidaInventario.TIPO_VENTA,
            estado=SalidaInventario.ESTADO_ACTIVA,
        )
        nota_saldo_pendiente = get_saldo_pendiente_nota(nota_seleccionada)

    if request.method == "POST":
        form = SaldoFavorAplicacionForm(request.POST)
        if form.is_valid():
            nota = get_object_or_404(
                SalidaInventario.objects.select_related("cliente_ref"),
                pk=form.cleaned_data["nota_id"],
                cliente_ref=cliente,
                tipo=SalidaInventario.TIPO_VENTA,
                estado=SalidaInventario.ESTADO_ACTIVA,
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


@login_required
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
