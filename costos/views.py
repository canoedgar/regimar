from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.decorators import permiso_requerido

from .forms import CategoriaGastoForm, CierreCosteoPeriodoForm, GastoForm, GastoPeriodoForm, PeriodoCosteoForm
from .models import CategoriaGasto, CierreCosteoPeriodo, Gasto, GastoPeriodo, PeriodoCosteo
from .services.distribucion import distribuir_gasto
from .services.cierres import calcular_resumen_costeo, generar_cierre_costeo
from .services.costeo_simple import cerrar_costeo_periodo, generar_costeo_periodo, obtener_resumen_periodo




def _periodos_costeo_queryset():
    return (
        PeriodoCosteo.objects.select_related("creado_por", "cerrado_por", "cancelado_por")
        .annotate(
            gastos_count=Count("gastos", distinct=True),
            almacenajes_count=Count("almacenajes", distinct=True),
            resultados_count=Count("resultados", distinct=True),
        )
        .order_by("-fecha_inicio", "-id")
    )


@permiso_requerido("costos.view_cierrecosteoperiodo")
def costos_home(request):
    return redirect("costos:periodos_costeo_list")


@permiso_requerido("costos.view_cierrecosteoperiodo")
def periodos_costeo_list(request):
    estado = (request.GET.get("estado") or "vigentes").strip()
    query = (request.GET.get("q") or "").strip()

    periodos = _periodos_costeo_queryset()
    if query:
        periodos = periodos.filter(Q(nombre__icontains=query) | Q(notas__icontains=query))

    if estado == "vigentes":
        periodos = periodos.exclude(estado=PeriodoCosteo.ESTADO_CANCELADO)
    elif estado in {PeriodoCosteo.ESTADO_ABIERTO, PeriodoCosteo.ESTADO_REVISION, PeriodoCosteo.ESTADO_CERRADO, PeriodoCosteo.ESTADO_CANCELADO}:
        periodos = periodos.filter(estado=estado)
    elif estado != "todos":
        estado = "vigentes"
        periodos = periodos.exclude(estado=PeriodoCosteo.ESTADO_CANCELADO)

    resumen = periodos.aggregate(
        total=Count("id"),
        abiertos=Count("id", filter=Q(estado=PeriodoCosteo.ESTADO_ABIERTO)),
        revision=Count("id", filter=Q(estado=PeriodoCosteo.ESTADO_REVISION)),
        cerrados=Count("id", filter=Q(estado=PeriodoCosteo.ESTADO_CERRADO)),
    )

    return render(
        request,
        "costos/periodos_costeo_list.html",
        {
            "periodos": periodos,
            "estado": estado,
            "query": query,
            "resumen": resumen,
            "puede_agregar": request.user.is_superuser or request.user.has_perm("costos.add_cierrecosteoperiodo"),
        },
    )


@permiso_requerido("costos.add_cierrecosteoperiodo")
def periodo_costeo_create(request):
    if request.method == "POST":
        form = PeriodoCosteoForm(request.POST)
        if form.is_valid():
            periodo = form.save(commit=False)
            periodo.creado_por = request.user if request.user.is_authenticated else None
            periodo.save()
            messages.success(request, "Periodo de costeo creado correctamente.")
            return redirect("costos:periodo_costeo_detail", pk=periodo.pk)
    else:
        form = PeriodoCosteoForm()
    return render(request, "costos/periodo_costeo_form.html", {"form": form, "modo_edicion": False})


@permiso_requerido("costos.change_cierrecosteoperiodo")
def periodo_costeo_edit(request, pk):
    periodo = get_object_or_404(PeriodoCosteo, pk=pk)
    if not periodo.puede_editarse:
        messages.warning(request, "Solo se pueden editar periodos abiertos o en revisión.")
        return redirect("costos:periodo_costeo_detail", pk=periodo.pk)

    if request.method == "POST":
        form = PeriodoCosteoForm(request.POST, instance=periodo)
        if form.is_valid():
            form.save()
            messages.success(request, "Periodo de costeo actualizado correctamente.")
            return redirect("costos:periodo_costeo_detail", pk=periodo.pk)
    else:
        form = PeriodoCosteoForm(instance=periodo)
    return render(request, "costos/periodo_costeo_form.html", {"form": form, "periodo": periodo, "modo_edicion": True})


@permiso_requerido("costos.view_cierrecosteoperiodo")
def periodo_costeo_detail(request, pk):
    periodo = get_object_or_404(_periodos_costeo_queryset(), pk=pk)
    gastos = periodo.gastos.select_related("almacen", "proveedor").all()[:8]
    almacenajes = periodo.almacenajes.select_related("producto", "almacen").all()[:8]
    resultados = periodo.resultados.select_related("producto").all()[:12]
    resumen = obtener_resumen_periodo(periodo)
    return render(
        request,
        "costos/periodo_costeo_detail.html",
        {
            "periodo": periodo,
            "gastos": gastos,
            "almacenajes": almacenajes,
            "resultados": resultados,
            "resumen": resumen,
            "puede_editar": request.user.is_superuser or request.user.has_perm("costos.change_cierrecosteoperiodo"),
            "puede_generar": request.user.is_superuser or request.user.has_perm("costos.add_cierrecosteoperiodo"),
            "puede_cerrar": request.user.is_superuser or request.user.has_perm("costos.add_cierrecosteoperiodo"),
            "puede_cancelar": request.user.is_superuser or request.user.has_perm("costos.puede_cancelar_cierre_costeo"),
        },
    )


@require_POST
@permiso_requerido("costos.add_cierrecosteoperiodo")
def periodo_costeo_generar(request, pk):
    periodo = get_object_or_404(PeriodoCosteo, pk=pk)
    try:
        resumen = generar_costeo_periodo(periodo, usuario=request.user)
        messages.success(
            request,
            f"Costeo generado: {resumen.total_productos} productos, margen real {resumen.margen_real}%.",
        )
        for advertencia in resumen.advertencias:
            messages.warning(request, advertencia)
    except ValidationError as exc:
        messages.warning(request, exc.messages[0] if hasattr(exc, "messages") else str(exc))
    return redirect("costos:periodo_costeo_detail", pk=periodo.pk)


@require_POST
@permiso_requerido("costos.add_cierrecosteoperiodo")
def periodo_costeo_cerrar(request, pk):
    periodo = get_object_or_404(PeriodoCosteo, pk=pk)
    try:
        cerrar_costeo_periodo(periodo, usuario=request.user)
        messages.success(request, "Periodo cerrado y costos sugeridos aprobados correctamente.")
    except ValidationError as exc:
        messages.warning(request, exc.messages[0] if hasattr(exc, "messages") else str(exc))
    return redirect("costos:periodo_costeo_detail", pk=periodo.pk)


@require_POST
@permiso_requerido("costos.puede_cancelar_cierre_costeo")
def periodo_costeo_cancelar(request, pk):
    periodo = get_object_or_404(PeriodoCosteo, pk=pk)
    motivo = (request.POST.get("motivo_cancelacion") or "").strip()
    try:
        periodo.cancelar(request.user, motivo=motivo)
        messages.success(request, "Periodo de costeo cancelado correctamente.")
    except ValidationError as exc:
        messages.warning(request, exc.messages[0] if hasattr(exc, "messages") else str(exc))
    return redirect("costos:periodo_costeo_detail", pk=periodo.pk)


@permiso_requerido("costos.view_gasto")
def gastos_periodo_list(request):
    periodo_id = (request.GET.get("periodo") or "").strip()
    tipo = (request.GET.get("tipo") or "").strip()
    estado = (request.GET.get("estado") or "activos").strip()

    gastos = GastoPeriodo.objects.select_related("periodo", "almacen", "proveedor").all().order_by("-fecha", "-id")
    periodo_id_int = None
    if periodo_id.isdigit():
        periodo_id_int = int(periodo_id)
        gastos = gastos.filter(periodo_id=periodo_id_int)
    else:
        periodo_id = ""

    tipos_validos = {value for value, _ in GastoPeriodo.TIPO_CHOICES}
    if tipo in tipos_validos:
        gastos = gastos.filter(tipo_gasto=tipo)
    else:
        tipo = ""

    if estado == "activos":
        gastos = gastos.filter(estado=GastoPeriodo.ESTADO_ACTIVO)
    elif estado == "cancelados":
        gastos = gastos.filter(estado=GastoPeriodo.ESTADO_CANCELADO)
    elif estado != "todos":
        estado = "activos"
        gastos = gastos.filter(estado=GastoPeriodo.ESTADO_ACTIVO)

    resumen = gastos.aggregate(total=Count("id"), importe_total=Sum("importe"))

    return render(
        request,
        "costos/gastos_periodo_list.html",
        {
            "gastos": gastos,
            "periodos": PeriodoCosteo.objects.exclude(estado=PeriodoCosteo.ESTADO_CANCELADO).order_by("-fecha_inicio"),
            "tipos_gasto": GastoPeriodo.TIPO_CHOICES,
            "periodo_id": periodo_id,
            "periodo_id_int": periodo_id_int,
            "tipo": tipo,
            "estado": estado,
            "resumen": resumen,
            "puede_agregar": request.user.is_superuser or request.user.has_perm("costos.add_gasto"),
            "puede_editar": request.user.is_superuser or request.user.has_perm("costos.change_gasto"),
            "puede_cancelar": request.user.is_superuser or request.user.has_perm("costos.puede_cancelar_gasto"),
        },
    )


@permiso_requerido("costos.add_gasto")
def gasto_periodo_create(request):
    periodo = None
    periodo_id = request.GET.get("periodo") or request.POST.get("periodo")
    if periodo_id and str(periodo_id).isdigit():
        periodo = PeriodoCosteo.objects.filter(pk=periodo_id).first()

    if request.method == "POST":
        form = GastoPeriodoForm(request.POST, periodo=periodo)
        if form.is_valid():
            gasto = form.save(commit=False)
            gasto.creado_por = request.user if request.user.is_authenticated else None
            gasto.save()
            messages.success(request, "Gasto del periodo guardado correctamente.")
            return redirect("costos:gastos_periodo_list")
    else:
        form = GastoPeriodoForm(periodo=periodo)
    return render(request, "costos/gasto_periodo_form.html", {"form": form, "modo_edicion": False})


@permiso_requerido("costos.change_gasto")
def gasto_periodo_edit(request, pk):
    gasto = get_object_or_404(GastoPeriodo, pk=pk)
    if not gasto.puede_editarse:
        messages.warning(request, "Solo se pueden editar gastos activos de periodos abiertos o en revisión.")
        return redirect("costos:gastos_periodo_list")
    if request.method == "POST":
        form = GastoPeriodoForm(request.POST, instance=gasto)
        if form.is_valid():
            form.save()
            messages.success(request, "Gasto del periodo actualizado correctamente.")
            return redirect("costos:gastos_periodo_list")
    else:
        form = GastoPeriodoForm(instance=gasto)
    return render(request, "costos/gasto_periodo_form.html", {"form": form, "gasto": gasto, "modo_edicion": True})


@require_POST
@permiso_requerido("costos.puede_cancelar_gasto")
def gasto_periodo_cancelar(request, pk):
    gasto = get_object_or_404(GastoPeriodo, pk=pk)
    motivo = (request.POST.get("motivo_cancelacion") or "").strip()
    try:
        gasto.cancelar(request.user, motivo=motivo)
        messages.success(request, "Gasto cancelado correctamente.")
    except ValidationError as exc:
        messages.warning(request, exc.messages[0] if hasattr(exc, "messages") else str(exc))
    return redirect("costos:gastos_periodo_list")


@permiso_requerido("costos.view_cierrecosteoperiodo")
def almacenaje_costeo_list(request):
    periodos = _periodos_costeo_queryset()
    return render(request, "costos/almacenaje_costeo_list.html", {"periodos": periodos})


@permiso_requerido("costos.view_cierrecosteoperiodo")
def almacenaje_costeo_detail(request, pk):
    periodo = get_object_or_404(PeriodoCosteo, pk=pk)
    almacenajes = periodo.almacenajes.select_related("almacen", "producto").all()
    resumen = almacenajes.aggregate(total=Sum("importe"), kg_total=Sum("kg_al_corte"), productos=Count("producto", distinct=True), almacenes=Count("almacen", distinct=True))
    return render(
        request,
        "costos/almacenaje_costeo_detail.html",
        {"periodo": periodo, "almacenajes": almacenajes, "resumen": resumen},
    )


@permiso_requerido("costos.view_cierrecosteoperiodo")
def resultados_costeo_list(request):
    periodos = _periodos_costeo_queryset()
    return render(request, "costos/resultados_costeo_list.html", {"periodos": periodos})


@permiso_requerido("costos.view_cierrecosteoperiodo")
def resultados_costeo_detail(request, pk):
    periodo = get_object_or_404(PeriodoCosteo, pk=pk)
    resultados = periodo.resultados.select_related("producto").all()
    resumen = obtener_resumen_periodo(periodo)
    return render(
        request,
        "costos/resultados_costeo_detail.html",
        {"periodo": periodo, "resultados": resultados, "resumen": resumen},
    )


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
