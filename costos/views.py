from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.decorators import permiso_requerido

from .forms import CategoriaGastoForm, CierreCosteoPeriodoForm, GastoForm
from .models import CategoriaGasto, CierreCosteoPeriodo, Gasto
from .services.distribucion import distribuir_gasto
from .services.cierres import calcular_resumen_costeo, generar_cierre_costeo


def _categorias_gasto_queryset():
    return CategoriaGasto.objects.all().order_by("tipo", "nombre")


@permiso_requerido("costos.view_categoriagasto")
def categorias_gasto_list(request):
    query = (request.GET.get("q") or "").strip()
    tipo = (request.GET.get("tipo") or "").strip()
    estado = (request.GET.get("estado") or "activos").strip()

    categorias = _categorias_gasto_queryset()

    if query:
        categorias = categorias.filter(
            Q(nombre__icontains=query)
            | Q(descripcion__icontains=query)
            | Q(nombre_normalizado__icontains=query)
        )

    tipos_validos = {value for value, _ in CategoriaGasto.TIPO_CHOICES}
    if tipo in tipos_validos:
        categorias = categorias.filter(tipo=tipo)
    else:
        tipo = ""

    if estado == "activos":
        categorias = categorias.filter(activo=True)
    elif estado == "inactivos":
        categorias = categorias.filter(activo=False)
    elif estado != "todos":
        estado = "activos"
        categorias = categorias.filter(activo=True)

    resumen = CategoriaGasto.objects.aggregate(
        total=Count("id"),
        activas=Count("id", filter=Q(activo=True)),
        distribuibles=Count("id", filter=Q(distribuible=True, activo=True)),
        no_distribuibles=Count("id", filter=Q(distribuible=False, activo=True)),
    )

    return render(
        request,
        "costos/categorias_gasto_list.html",
        {
            "categorias": categorias,
            "query": query,
            "tipo": tipo,
            "estado": estado,
            "tipos": CategoriaGasto.TIPO_CHOICES,
            "resumen": resumen,
            "puede_agregar": request.user.is_superuser or request.user.has_perm("costos.add_categoriagasto"),
            "puede_editar": request.user.is_superuser or request.user.has_perm("costos.change_categoriagasto"),
            "puede_activar": request.user.is_superuser or request.user.has_perm("costos.puede_activar_categoriagasto"),
        },
    )


@permiso_requerido("costos.add_categoriagasto")
def categoria_gasto_create(request):
    if request.method == "POST":
        form = CategoriaGastoForm(request.POST)
        if form.is_valid():
            categoria = form.save()
            messages.success(request, f"Categoría de gasto '{categoria.nombre}' creada correctamente.")
            return redirect("costos:categorias_gasto_list")
    else:
        form = CategoriaGastoForm()

    return render(
        request,
        "costos/categoria_gasto_form.html",
        {
            "form": form,
            "modo_edicion": False,
        },
    )


@permiso_requerido("costos.change_categoriagasto")
def categoria_gasto_edit(request, pk):
    categoria = get_object_or_404(CategoriaGasto, pk=pk)

    if request.method == "POST":
        form = CategoriaGastoForm(request.POST, instance=categoria)
        if form.is_valid():
            categoria = form.save()
            messages.success(request, f"Categoría de gasto '{categoria.nombre}' actualizada correctamente.")
            return redirect("costos:categorias_gasto_list")
    else:
        form = CategoriaGastoForm(instance=categoria)

    return render(
        request,
        "costos/categoria_gasto_form.html",
        {
            "form": form,
            "modo_edicion": True,
            "categoria": categoria,
        },
    )


@require_POST
@permiso_requerido("costos.puede_activar_categoriagasto")
def categoria_gasto_toggle_activo(request, pk):
    categoria = get_object_or_404(CategoriaGasto, pk=pk)
    categoria.activo = not categoria.activo
    categoria.save(update_fields=["activo", "metodo_default_distribucion", "actualizado_en"])

    estado = "activada" if categoria.activo else "desactivada"
    messages.success(request, f"Categoría de gasto '{categoria.nombre}' {estado} correctamente.")
    return redirect("costos:categorias_gasto_list")


def _gastos_queryset():
    return (
        Gasto.objects.select_related(
            "categoria",
            "proveedor",
            "entrada_inventario",
            "almacen",
            "creado_por",
            "aplicado_por",
            "cancelado_por",
        )
        .all()
        .annotate(
            distribuciones_count=Count("distribuciones", distinct=True),
            importe_distribuido_list=Sum("distribuciones__importe_asignado"),
        )
        .order_by("-fecha", "-creado_en")
    )


def _usuario_puede_ver_gasto(user):
    return user.is_superuser or user.has_perm("costos.view_gasto")


def _usuario_puede_agregar_gasto(user):
    return user.is_superuser or user.has_perm("costos.add_gasto")


def _usuario_puede_editar_gasto(user):
    return user.is_superuser or user.has_perm("costos.change_gasto")


def _usuario_puede_aplicar_gasto(user):
    return user.is_superuser or user.has_perm("costos.puede_aplicar_gasto")


def _usuario_puede_cancelar_gasto(user):
    return user.is_superuser or user.has_perm("costos.puede_cancelar_gasto")


def _usuario_puede_recalcular_distribucion(user):
    return user.is_superuser or user.has_perm("costos.puede_aplicar_gasto")


@permiso_requerido("costos.view_gasto")
def gastos_list(request):
    query = (request.GET.get("q") or "").strip()
    categoria_id = (request.GET.get("categoria") or "").strip()
    estado = (request.GET.get("estado") or "vigentes").strip()
    fecha_inicio = (request.GET.get("fecha_inicio") or "").strip()
    fecha_fin = (request.GET.get("fecha_fin") or "").strip()

    gastos = _gastos_queryset()

    if query:
        gastos = gastos.filter(
            Q(folio__icontains=query)
            | Q(referencia__icontains=query)
            | Q(descripcion__icontains=query)
            | Q(observaciones__icontains=query)
            | Q(categoria__nombre__icontains=query)
            | Q(proveedor__nombre__icontains=query)
            | Q(entrada_inventario__folio__icontains=query)
        )

    categoria_id_int = None
    if categoria_id.isdigit():
        categoria_id_int = int(categoria_id)
        gastos = gastos.filter(categoria_id=categoria_id_int)
    else:
        categoria_id = ""

    if fecha_inicio:
        gastos = gastos.filter(fecha__gte=fecha_inicio)
    if fecha_fin:
        gastos = gastos.filter(fecha__lte=fecha_fin)

    if estado == "vigentes":
        gastos = gastos.exclude(estado=Gasto.ESTADO_CANCELADO)
    elif estado == "borradores":
        gastos = gastos.filter(estado=Gasto.ESTADO_BORRADOR)
    elif estado == "aplicados":
        gastos = gastos.filter(estado=Gasto.ESTADO_APLICADO)
    elif estado == "cancelados":
        gastos = gastos.filter(estado=Gasto.ESTADO_CANCELADO)
    elif estado != "todos":
        estado = "vigentes"
        gastos = gastos.exclude(estado=Gasto.ESTADO_CANCELADO)

    resumen = gastos.aggregate(
        total=Count("id"),
        borradores=Count("id", filter=Q(estado=Gasto.ESTADO_BORRADOR)),
        aplicados=Count("id", filter=Q(estado=Gasto.ESTADO_APLICADO)),
        cancelados=Count("id", filter=Q(estado=Gasto.ESTADO_CANCELADO)),
        importe_total=Sum("importe"),
        importe_aplicado=Sum("importe", filter=Q(estado=Gasto.ESTADO_APLICADO)),
    )

    return render(
        request,
        "costos/gastos_list.html",
        {
            "gastos": gastos,
            "categorias": CategoriaGasto.objects.filter(activo=True).order_by("tipo", "nombre"),
            "query": query,
            "categoria_id": categoria_id,
            "categoria_id_int": categoria_id_int,
            "estado": estado,
            "fecha_inicio": fecha_inicio,
            "fecha_fin": fecha_fin,
            "resumen": resumen,
            "puede_agregar": _usuario_puede_agregar_gasto(request.user),
            "puede_editar": _usuario_puede_editar_gasto(request.user),
            "puede_aplicar": _usuario_puede_aplicar_gasto(request.user),
            "puede_cancelar": _usuario_puede_cancelar_gasto(request.user),
        },
    )


@permiso_requerido("costos.add_gasto")
def gasto_create(request):
    if request.method == "POST":
        form = GastoForm(request.POST)
        if form.is_valid():
            gasto = form.save(commit=False)
            gasto.creado_por = request.user if request.user.is_authenticated else None
            gasto.save()
            accion = request.POST.get("accion")
            if accion == "guardar_aplicar":
                if _usuario_puede_aplicar_gasto(request.user):
                    try:
                        gasto.aplicar(request.user)
                        messages.success(request, f"Gasto {gasto.folio} guardado y aplicado correctamente.")
                    except ValidationError as exc:
                        messages.warning(request, exc.messages[0] if hasattr(exc, "messages") else str(exc))
                else:
                    messages.warning(request, "Gasto guardado en borrador. No tienes permiso para aplicarlo.")
            else:
                messages.success(request, f"Gasto {gasto.folio} guardado en borrador correctamente.")
            return redirect("costos:gasto_detail", pk=gasto.pk)
    else:
        form = GastoForm()

    return render(
        request,
        "costos/gasto_form.html",
        {
            "form": form,
            "modo_edicion": False,
            "puede_aplicar": _usuario_puede_aplicar_gasto(request.user),
            "categorias_json": _categorias_para_js(),
        },
    )


@permiso_requerido("costos.view_gasto")
def gasto_detail(request, pk):
    gasto = get_object_or_404(_gastos_queryset(), pk=pk)
    distribuciones = gasto.distribuciones.select_related("producto", "almacen").all()
    resumen_distribucion = distribuciones.aggregate(
        total_base=Sum("cantidad_base"),
        total_importe=Sum("importe_asignado"),
        productos=Count("producto", distinct=True),
        almacenes=Count("almacen", distinct=True),
    )
    return render(
        request,
        "costos/gasto_detail.html",
        {
            "gasto": gasto,
            "distribuciones": distribuciones,
            "resumen_distribucion": resumen_distribucion,
            "puede_editar": _usuario_puede_editar_gasto(request.user),
            "puede_aplicar": _usuario_puede_aplicar_gasto(request.user),
            "puede_cancelar": _usuario_puede_cancelar_gasto(request.user),
            "puede_recalcular_distribucion": _usuario_puede_recalcular_distribucion(request.user),
        },
    )


@permiso_requerido("costos.change_gasto")
def gasto_edit(request, pk):
    gasto = get_object_or_404(Gasto, pk=pk)
    if not gasto.puede_editarse:
        messages.warning(request, "Solo se pueden editar gastos en borrador.")
        return redirect("costos:gasto_detail", pk=gasto.pk)

    if request.method == "POST":
        form = GastoForm(request.POST, instance=gasto)
        if form.is_valid():
            gasto = form.save()
            accion = request.POST.get("accion")
            if accion == "guardar_aplicar":
                if _usuario_puede_aplicar_gasto(request.user):
                    try:
                        gasto.aplicar(request.user)
                        messages.success(request, f"Gasto {gasto.folio} actualizado y aplicado correctamente.")
                    except ValidationError as exc:
                        messages.warning(request, exc.messages[0] if hasattr(exc, "messages") else str(exc))
                else:
                    messages.warning(request, "Gasto actualizado en borrador. No tienes permiso para aplicarlo.")
            else:
                messages.success(request, f"Gasto {gasto.folio} actualizado correctamente.")
            return redirect("costos:gasto_detail", pk=gasto.pk)
    else:
        form = GastoForm(instance=gasto)

    return render(
        request,
        "costos/gasto_form.html",
        {
            "form": form,
            "gasto": gasto,
            "modo_edicion": True,
            "puede_aplicar": _usuario_puede_aplicar_gasto(request.user),
            "categorias_json": _categorias_para_js(),
        },
    )


@require_POST
@permiso_requerido("costos.puede_aplicar_gasto")
def gasto_aplicar(request, pk):
    gasto = get_object_or_404(Gasto, pk=pk)
    try:
        gasto.aplicar(request.user)
        messages.success(request, f"Gasto {gasto.folio} aplicado correctamente.")
    except ValidationError as exc:
        messages.warning(request, exc.messages[0] if hasattr(exc, "messages") else str(exc))
    return redirect("costos:gasto_detail", pk=gasto.pk)


@require_POST
@permiso_requerido("costos.puede_cancelar_gasto")
def gasto_cancelar(request, pk):
    gasto = get_object_or_404(Gasto, pk=pk)
    motivo = (request.POST.get("motivo_cancelacion") or "").strip()
    try:
        gasto.cancelar(request.user, motivo=motivo)
        messages.success(request, f"Gasto {gasto.folio} cancelado correctamente.")
    except ValidationError as exc:
        messages.warning(request, exc.messages[0] if hasattr(exc, "messages") else str(exc))
    return redirect("costos:gasto_detail", pk=gasto.pk)


@require_POST
@permiso_requerido("costos.puede_aplicar_gasto")
def gasto_recalcular_distribucion(request, pk):
    gasto = get_object_or_404(Gasto.objects.select_related("categoria", "almacen", "entrada_inventario"), pk=pk)
    try:
        distribuciones = distribuir_gasto(gasto)
        if distribuciones:
            messages.success(request, f"Distribución recalculada correctamente para {gasto.folio}.")
        else:
            messages.info(request, "El gasto no requiere distribución automática con el método configurado.")
    except ValidationError as exc:
        messages.warning(request, exc.messages[0] if hasattr(exc, "messages") else str(exc))
    return redirect("costos:gasto_detail", pk=gasto.pk)


def _categorias_para_js():
    return {
        str(categoria.pk): {
            "distribuible": categoria.distribuible,
            "metodo": categoria.metodo_default_distribucion,
        }
        for categoria in CategoriaGasto.objects.all()
    }


def _cierres_queryset():
    return (
        CierreCosteoPeriodo.objects.select_related("creado_por", "cancelado_por")
        .all()
        .order_by("-periodo_inicio", "-folio")
    )


def _usuario_puede_ver_cierre(user):
    return user.is_superuser or user.has_perm("costos.view_cierrecosteoperiodo")


def _usuario_puede_agregar_cierre(user):
    return user.is_superuser or user.has_perm("costos.add_cierrecosteoperiodo")


def _usuario_puede_cancelar_cierre(user):
    return user.is_superuser or user.has_perm("costos.puede_cancelar_cierre_costeo")


@permiso_requerido("costos.view_cierrecosteoperiodo")
def cierres_costeo_list(request):
    estado = (request.GET.get("estado") or "vigentes").strip()
    fecha_inicio = (request.GET.get("fecha_inicio") or "").strip()
    fecha_fin = (request.GET.get("fecha_fin") or "").strip()

    cierres = _cierres_queryset()

    if fecha_inicio:
        cierres = cierres.filter(periodo_fin__gte=fecha_inicio)
    if fecha_fin:
        cierres = cierres.filter(periodo_inicio__lte=fecha_fin)

    if estado == "vigentes":
        cierres = cierres.exclude(estado=CierreCosteoPeriodo.ESTADO_CANCELADO)
    elif estado == "cancelados":
        cierres = cierres.filter(estado=CierreCosteoPeriodo.ESTADO_CANCELADO)
    elif estado != "todos":
        estado = "vigentes"
        cierres = cierres.exclude(estado=CierreCosteoPeriodo.ESTADO_CANCELADO)

    resumen = cierres.aggregate(
        total=Count("id"),
        cancelados=Count("id", filter=Q(estado=CierreCosteoPeriodo.ESTADO_CANCELADO)),
        venta_total=Sum("total_ventas"),
        costo_real_total=Sum("total_costo_real"),
        utilidad_real=Sum("utilidad_real"),
    )

    return render(
        request,
        "costos/cierres_costeo_list.html",
        {
            "cierres": cierres,
            "estado": estado,
            "fecha_inicio": fecha_inicio,
            "fecha_fin": fecha_fin,
            "resumen": resumen,
            "puede_agregar": _usuario_puede_agregar_cierre(request.user),
            "puede_cancelar": _usuario_puede_cancelar_cierre(request.user),
        },
    )


@permiso_requerido("costos.add_cierrecosteoperiodo")
def cierre_costeo_create(request):
    resumen_costeo = None
    form = CierreCosteoPeriodoForm(request.POST or request.GET or None)

    if request.method == "POST":
        if form.is_valid():
            try:
                cierre = generar_cierre_costeo(
                    form.cleaned_data["periodo_inicio"],
                    form.cleaned_data["periodo_fin"],
                    usuario=request.user,
                    notas=form.cleaned_data.get("notas") or "",
                )
                messages.success(request, f"Cierre de costeo {cierre.folio} generado correctamente.")
                return redirect("costos:cierre_costeo_detail", pk=cierre.pk)
            except ValidationError as exc:
                messages.warning(request, exc.messages[0] if hasattr(exc, "messages") else str(exc))
                try:
                    resumen_costeo = calcular_resumen_costeo(
                        form.cleaned_data["periodo_inicio"],
                        form.cleaned_data["periodo_fin"],
                    )
                except ValidationError:
                    resumen_costeo = None
    else:
        if request.GET.get("periodo_inicio") and request.GET.get("periodo_fin") and form.is_valid():
            try:
                resumen_costeo = calcular_resumen_costeo(
                    form.cleaned_data["periodo_inicio"],
                    form.cleaned_data["periodo_fin"],
                )
            except ValidationError as exc:
                messages.warning(request, exc.messages[0] if hasattr(exc, "messages") else str(exc))

    return render(
        request,
        "costos/cierre_costeo_form.html",
        {
            "form": form,
            "resumen_costeo": resumen_costeo,
        },
    )


@permiso_requerido("costos.view_cierrecosteoperiodo")
def cierre_costeo_detail(request, pk):
    cierre = get_object_or_404(_cierres_queryset(), pk=pk)
    productos = cierre.productos.select_related("producto").all()
    return render(
        request,
        "costos/cierre_costeo_detail.html",
        {
            "cierre": cierre,
            "productos": productos,
            "puede_cancelar": _usuario_puede_cancelar_cierre(request.user),
        },
    )


@require_POST
@permiso_requerido("costos.puede_cancelar_cierre_costeo")
def cierre_costeo_cancelar(request, pk):
    cierre = get_object_or_404(CierreCosteoPeriodo, pk=pk)
    motivo = (request.POST.get("motivo_cancelacion") or "").strip()
    try:
        cierre.cancelar(request.user, motivo=motivo)
        messages.success(request, f"Cierre de costeo {cierre.folio} cancelado correctamente.")
    except ValidationError as exc:
        messages.warning(request, exc.messages[0] if hasattr(exc, "messages") else str(exc))
    return redirect("costos:cierre_costeo_detail", pk=cierre.pk)
