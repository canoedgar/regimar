from django.db import transaction, IntegrityError
from django.contrib import messages
from django.shortcuts import render, redirect

from catalogos.models import Almacen, Proveedor, Producto

from ..models import EntradaInventario, EntradaInventarioDetalle
from ..forms import EntradaOCFacturaUploadForm, ConciliacionFormSet

from ..utils import get_almacen_default

from ..services.folios import next_folio_movimiento
from ..services.cfdi import parse_cfdi_header, parse_cfdi_xml
from ..services.stock import aplicar_entrada_con_costo

from datetime import datetime

from decimal import Decimal

@transaction.atomic
def entrada_ocf_create(request):
    step = request.POST.get("step", "upload")

    # Helpers: proveedores list + match por RFC/nombre
    def _proveedores_todos():
        return Proveedor.objects.all().order_by("nombre")

    def _match_proveedor(header):
        """
        Busca proveedor por RFC (preferente) y luego por nombre.
        """
        if not header:
            return None

        rfc = (header.get("proveedor_rfc") or "").strip()
        nombre = (header.get("proveedor_nombre") or "").strip()

        proveedor_bd = None
        if rfc:
            proveedor_bd = Proveedor.objects.filter(rfc__iexact=rfc).first()
        if not proveedor_bd and nombre:
            proveedor_bd = Proveedor.objects.filter(nombre__iexact=nombre).first()
        return proveedor_bd

    # PASO 1: subir XML
    if request.method == "POST" and step == "upload":

        # Limpia contexto anterior para evitar XML "pegado"
        for k in ("ocf_xml_conceptos", "ocf_xml_header", "ocf_xml_text", "ocf_producto_creado", "ocf_almacen_id"):
            request.session.pop(k, None)
        
        almacenes_qs = Almacen.objects.filter(es_activo=True).order_by("tipo", "nombre")
        almacen_default = get_almacen_default()

        form = EntradaOCFacturaUploadForm(request.POST, request.FILES)

        if not form.is_valid():
            return render(request, "inventarios/entrada_ocf_form.html", {
                "step": "upload",
                "form_upload": form,
            })

        xml_file = form.cleaned_data["xml_archivo"]
        xml_bytes = xml_file.read()
        xml_text = xml_bytes.decode("utf-8")
        
        # Encabezado desde XML
        header_xml = parse_cfdi_header(xml_text)

        # Buscar proveedor en BD por RFC/nombre
        proveedor_bd = _match_proveedor(header_xml)

        # Folio interno del sistema para OCF (mostrar en UI desde el inicio)
        folio_sistema = next_folio_movimiento(tipo="OCF", width=6)       

        header_xml["folio_sistema"] = folio_sistema
        header_xml["factura_folio"] = header_xml.get("folio", "")                      

        # Conceptos
        conceptos = parse_cfdi_xml(xml_text)
        if not conceptos:
            messages.error(request, "El XML no contiene conceptos de productos.")
            return render(request, "inventarios/entrada_ocf_form.html", {
                "step": "upload",
                "form_upload": form,
            })

        # Inicial para conciliación de productos
        initial = []
        for c in conceptos:
            producto_encontrado = None
            if c["clave_sat"]:
                producto_encontrado = Producto.objects.filter(
                    clave_sat=c["clave_sat"]
                ).first()
            if not producto_encontrado and c["descripcion"]:
                producto_encontrado = Producto.objects.filter(
                    nombre__iexact=c["descripcion"]
                ).first()

            initial.append({
                "clave_sat_xml": c["clave_sat"],
                "descripcion_xml": c["descripcion"],
                "cantidad_xml": c["cantidad"],
                "valor_unitario_xml": c["valor_unitario"],
                "producto": producto_encontrado.pk if producto_encontrado else None,
            })

        formset = ConciliacionFormSet(initial=initial)

        request.session["ocf_xml_conceptos"] = initial
        request.session["ocf_xml_header"] = header_xml
        request.session["ocf_xml_text"] = xml_text
        # Default de almacén para este proceso
        request.session["ocf_almacen_id"] = almacen_default.id if almacen_default else ""        

        return render(request, "inventarios/entrada_ocf_form.html", {
            "step": "conciliacion",
            "header": header_xml,
            "xml_contenido": xml_text,
            "formset": formset,
            "proveedor_bd": proveedor_bd,
            "proveedores_todos": _proveedores_todos(),
            "almacenes": almacenes_qs,
            "almacen": almacen_default,
            "almacen_id": request.session.get("ocf_almacen_id"),
        })

    # GET: si hay contexto en sesión, volver a conciliación
    if request.method == "GET":
        almacenes_qs = Almacen.objects.filter(es_activo=True).order_by("tipo", "nombre")

        # Tomar almacén de sesión si existe, si no usar default
        almacen_default = get_almacen_default()
        ses_alm_id = request.session.get("ocf_almacen_id")
        if ses_alm_id and str(ses_alm_id).isdigit():
            almacen_default = almacenes_qs.filter(pk=int(ses_alm_id)).first() or almacen_default

        if request.GET.get("reset") == "1":
            for k in ("ocf_xml_conceptos", "ocf_xml_header", "ocf_xml_text", "ocf_producto_creado", "ocf_almacen_id"):
                request.session.pop(k, None)

            form_upload = EntradaOCFacturaUploadForm()
            return render(request, "inventarios/entrada_ocf_form.html", {
                "step": "upload",
                "form_upload": form_upload,
            })

        initial = request.session.get("ocf_xml_conceptos")
        header_xml = request.session.get("ocf_xml_header")
        xml_text = request.session.get("ocf_xml_text")

        if initial and header_xml and xml_text:
            created = request.session.pop("ocf_producto_creado", None)
            if created:
                i = created["idx"]
                pid = created["producto_id"]
                if 0 <= i < len(initial):
                    initial[i]["producto"] = pid

                request.session["ocf_xml_conceptos"] = initial

            formset = ConciliacionFormSet(initial=initial)

            proveedor_bd = _match_proveedor(header_xml)

            # Seguridad: si el header guardado no trae folio_sistema, generarlo
            if header_xml and not header_xml.get("folio_sistema"):
                header_xml["folio_sistema"] = next_folio_movimiento(tipo="OCF", width=6)
                request.session["ocf_xml_header"] = header_xml


            return render(request, "inventarios/entrada_ocf_form.html", {
                "step": "conciliacion",
                "header": header_xml,
                "xml_contenido": xml_text,
                "formset": formset,
                "almacenes": almacenes_qs,
                "almacen": almacen_default,
                "almacen_id": ses_alm_id,
                "proveedor_bd": proveedor_bd,
                "proveedores_todos": _proveedores_todos(),
            })

    def _header_para_render(fallback: dict | None = None) -> dict:
        """
        Regresa el header 'oficial' para la UI:
        - preferimos el de sesión (viene del XML y trae folio_sistema, factura_folio, etc.)
        - si no existe, usamos fallback (por seguridad)
        """
        h = (request.session.get("ocf_xml_header") or {}).copy()
        if not h and fallback:
            h = dict(fallback)

        # Asegurar folio_sistema
        if not h.get("folio_sistema"):
            h["folio_sistema"] = (request.POST.get("folio") or "").strip() or next_folio_movimiento(tipo="OCF", width=6)

        # Asegurar factura_folio (folio CFDI original)
        if not h.get("factura_folio"):
            # Si parse_cfdi_header trae 'folio' (CFDI) lo usamos
            h["factura_folio"] = h.get("folio", "") or (request.POST.get("factura_folio") or "")

        # Fecha: mantener display si existe; si solo hay fecha iso, crear display simple
        # (idealmente parse_cfdi_header debería traer fecha_display, pero esto evita regresos feos)
        if not h.get("fecha_display") and h.get("fecha"):
            h["fecha_display"] = h["fecha"]

        return h


    # PASO 2: guardar conciliación + crear proveedor si es necesario
    if request.method == "POST" and step == "conciliacion":
        xml_text = request.POST.get("xml_contenido", "")

        folio = (request.POST.get("folio") or "").strip()
        if not folio:
            folio = next_folio_movimiento(tipo="OCF", width=6)
        fecha_raw = request.POST.get("fecha") or ""
        uuid_factura = request.POST.get("uuid")
        proveedor_nombre_xml = request.POST.get("proveedor_nombre_xml")
        proveedor_rfc_xml = request.POST.get("proveedor_rfc_xml")
        observaciones = request.POST.get("observaciones", "")

        almacenes_qs = Almacen.objects.filter(es_activo=True).order_by("tipo", "nombre")
        almacen = get_almacen_default()
        almacen_id = (request.POST.get("almacen_id") or request.session.get("ocf_almacen_id") or "").strip()
        if almacen_id and str(almacen_id).isdigit():
            almacen = almacenes_qs.filter(pk=int(almacen_id)).first() or almacen
        # Persistir selección
        request.session["ocf_almacen_id"] = almacen.id if almacen else ""

        initial = request.session.get("ocf_xml_conceptos", [])

        created = request.session.pop("ocf_producto_creado", None)
        if created:
            i = created["idx"]
            pid = created["producto_id"]
            initial = request.session.get("ocf_xml_conceptos", [])
            if i < len(initial):
                initial[i]["producto"] = pid

        formset = ConciliacionFormSet(request.POST, initial=initial)

        fecha_str = fecha_raw
        if "T" in fecha_str:
            fecha_str = fecha_str.split("T")[0]

        try:
            fecha_cfdi = datetime.strptime(fecha_str, "%Y-%m-%d").date()
        except ValueError:
            fecha_cfdi = None

        # Si el formset es inválido, regresamos a conciliación
        if not formset.is_valid():
            header_xml = _header_para_render({
                "uuid": uuid_factura,
                "proveedor_nombre": proveedor_nombre_xml,
                "proveedor_rfc": proveedor_rfc_xml,
            })            
            messages.error(request, formset.errors)
            return render(request, "inventarios/entrada_ocf_form.html", {
                "step": "conciliacion",
                "header": header_xml,
                "xml_contenido": xml_text,
                "formset": formset,
                "almacenes": almacenes_qs,
                "almacen": almacen,
                "almacen_id": almacen_id,
                "proveedor_bd": _match_proveedor(header_xml),
                "proveedores_todos": _proveedores_todos(),
            })                


        # Validar si este UUID ya fue registrado
        if uuid_factura and EntradaInventario.objects.filter(uuid_factura=uuid_factura).exists():
            header_xml = _header_para_render({
                "uuid": uuid_factura,
                "proveedor_nombre": proveedor_nombre_xml,
                "proveedor_rfc": proveedor_rfc_xml,
            })
            messages.error(
                request,                                
                f"La factura con UUID {uuid_factura} ya fue ingresada previamente. "
                "No es posible registrar una entrada duplicada."
            )
            return render(request, "inventarios/entrada_ocf_form.html", {
                "step": "conciliacion",
                "header": header_xml,
                "xml_contenido": xml_text,
                "formset": formset,
                "almacenes": almacenes_qs,
                "almacen": almacen,
                "almacen_id": almacen_id,
                "proveedor_bd": _match_proveedor(header_xml),
                "proveedores_todos": _proveedores_todos(),
            })

        conciliados = 0
        excluidos = 0

        for f in formset:
            cd = getattr(f, "cleaned_data", {}) or {}
            if not cd:
                continue

            if cd.get("excluir"):
                excluidos += 1
                continue

            # Si no excluye, el clean ya garantiza producto o crear_nuevo;
            # pero producto puede venir None si crear_nuevo se maneja en otra vista.
            # En fase 1, lo que se guarda a inventario debe tener producto real.
            if cd.get("producto"):
                conciliados += 1
            else:
                # Esto representa "pendiente" real para inventario
                messages.error(request, "Hay renglones inventariables sin producto conciliado. Concílialos o exclúyelos.")


        proveedor = None
        proveedor_id = request.POST.get("proveedor_id")
        crear_proveedor = request.POST.get("crear_proveedor") == "on"

        header_tmp = {
            "proveedor_rfc": proveedor_rfc_xml,
            "proveedor_nombre": proveedor_nombre_xml,
        }
        proveedor_existente = _match_proveedor(header_tmp)

        # Si ya existe proveedor por RFC/nombre, NO permitir crear uno nuevo
        if proveedor_existente:
            crear_proveedor = False

        # Si seleccionó un proveedor del combo, se respeta
        if proveedor_id:
            try:
                proveedor = Proveedor.objects.get(pk=proveedor_id)
            except Proveedor.DoesNotExist:
                proveedor = None

        # Si no seleccionó nada, pero existe por RFC/nombre, usarlo automáticamente
        if not proveedor and proveedor_existente:
            proveedor = proveedor_existente

        # Solo si NO existe y el usuario lo pidió, crear proveedor
        if not proveedor and crear_proveedor:
            proveedor_nombre_form = request.POST.get("proveedor_nombre_nuevo") or proveedor_nombre_xml
            proveedor_rfc_form = request.POST.get("proveedor_rfc_nuevo") or proveedor_rfc_xml

            proveedor = Proveedor.objects.create(
                nombre=proveedor_nombre_form,
                rfc=proveedor_rfc_form,
            )

        if not proveedor:
            header_xml = _header_para_render({
                "uuid": uuid_factura,
                "proveedor_nombre": proveedor_nombre_xml,
                "proveedor_rfc": proveedor_rfc_xml,
            })
            messages.error(request, "Selecciona un proveedor (o créalo) antes de guardar.")
            return render(request, "inventarios/entrada_ocf_form.html", {
                "step": "conciliacion",
                "header": header_xml,
                "xml_contenido": xml_text,
                "formset": formset,
                "almacenes": almacenes_qs,
                "almacen": almacen,
                "almacen_id": almacen_id,
                "proveedor_bd": _match_proveedor(header_xml),
                "proveedores_todos": _proveedores_todos(),
            })
               

        try:
            if not fecha_cfdi:
                raise IntegrityError("Fecha CFDI inválida")

            if not almacen:
                raise IntegrityError("No se pudo determinar un almacén")

            if conciliados <= 0:
                raise IntegrityError(
                    "La factura no contiene conceptos inventariables conciliados. "
                    "Excluye servicios/fletes o concilia productos."
                )

            entrada = EntradaInventario.objects.create(
                folio=folio,
                fecha=fecha_cfdi,
                proveedor=proveedor,
                uuid_factura=uuid_factura,
                observaciones=observaciones,
                tipo=EntradaInventario.TIPO_OC_CON_FACTURA,
                tiene_xml=True,
                xml_contenido=xml_text,
                almacen=almacen,
            )

            # --- 1) Crear detalles y actualizar inventario/costos ---
            for f in formset:
                cd = f.cleaned_data

                if cd.get("excluir"):
                    continue

                producto = cd.get("producto")
                if not producto:
                    raise IntegrityError("Línea inventariable sin producto conciliado.")

                cantidad = cd.get("cantidad_xml") or Decimal("0")
                costo_unitario = cd.get("valor_unitario_xml") or Decimal("0")

                if cantidad <= 0:
                    raise IntegrityError("Cantidad inválida en una línea conciliada")

                # Crear detalle
                EntradaInventarioDetalle.objects.create(
                    entrada=entrada,
                    producto=producto,
                    almacen=almacen,
                    cantidad=cantidad,
                    costo_unitario=costo_unitario,
                )

                aplicar_entrada_con_costo(
                    producto_id=producto.id,
                    almacen_id=almacen.id,
                    cantidad=cantidad,
                    costo_unitario=costo_unitario,
                    usuario=request.user,
                    motivo_bitacora="Entrada desde factura XML",
                )

        except IntegrityError as e:
            if "inventarios_entradainventario.folio" in str(e):
                messages.error(
                    request,
                    f"Ya existe una entrada de inventario con el folio {folio}. "
                    "Por favor, modifica el folio antes de guardar."
                )
            else:
                messages.error(request, str(e).strip())

            header_xml = _header_para_render({
                "uuid": uuid_factura,
                "proveedor_nombre": proveedor_nombre_xml,
                "proveedor_rfc": proveedor_rfc_xml,
            })

            return render(request, "inventarios/entrada_ocf_form.html", {
                "step": "conciliacion",
                "header": header_xml,
                "xml_contenido": xml_text,
                "formset": formset,
                "almacenes": almacenes_qs,
                "almacen": almacen,
                "almacen_id": almacen_id,
                "proveedor_bd": proveedor,
                "proveedores_todos": _proveedores_todos(),
            })

        except IntegrityError as e:
            if "inventarios_entradainventario.folio" in str(e) or "inventarios_entradainventario_folio" in str(e):
                messages.error(
                    request,
                    f"Ya existe una entrada de inventario con el folio {folio}. "
                    "Por favor, modifica el folio antes de guardar."
                )
            else:
                messages.error(request, str(e).strip())

            header_xml = _header_para_render({
                "uuid": uuid_factura,
                "proveedor_nombre": proveedor_nombre_xml,
                "proveedor_rfc": proveedor_rfc_xml,
            })

            return render(request, "inventarios/entrada_ocf_form.html", {
                "step": "conciliacion",
                "header": header_xml,
                "xml_contenido": xml_text,
                "formset": formset,
                "almacenes": almacenes_qs,
                "almacen": almacen,
                "almacen_id": almacen_id,
                "proveedor_bd": proveedor,
                "proveedores_todos": _proveedores_todos(),
            })

        except IntegrityError as e:
            if "inventarios_entradainventario.folio" in str(e) or "inventarios_entradainventario_folio" in str(e):
                messages.error(
                    request,
                    f"Ya existe una entrada de inventario con el folio {folio}. "
                    "Por favor, modifica el folio antes de guardar."
                )
            else:
                messages.error(
                    request,
                    str(e).strip()
                )

            header_xml = _header_para_render({
                "uuid": uuid_factura,
                "proveedor_nombre": proveedor_nombre_xml,
                "proveedor_rfc": proveedor_rfc_xml,
            })


            return render(request, "inventarios/entrada_ocf_form.html", {
                "step": "conciliacion",
                "header": header_xml,
                "xml_contenido": xml_text,
                "formset": formset,
                "almacenes": almacenes_qs,
                "almacen": almacen,
                "almacen_id": almacen_id,
                "proveedor_bd": proveedor,
                "proveedores_todos": _proveedores_todos(),
            })

        # Limpiar sesión para que NO se quede el XML anterior
        for k in ("ocf_xml_conceptos", "ocf_xml_header", "ocf_xml_text", "ocf_producto_creado", "ocf_almacen_id"):
            request.session.pop(k, None)

        messages.success(request, f"Entrada {entrada.folio} registrada y conciliada correctamente.")
        return redirect("entradas_list")


    # GET inicial: solo subir XML
    form_upload = EntradaOCFacturaUploadForm()
    return render(request, "inventarios/entrada_ocf_form.html", {
        "step": "upload",
        "form_upload": form_upload,
    })
