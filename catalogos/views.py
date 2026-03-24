# catalogos/views.py
from openpyxl import load_workbook
from urllib.parse import urlencode

from decimal import Decimal, InvalidOperation

from django.http import JsonResponse

from django.core.exceptions import ValidationError

from django.shortcuts import render, redirect, get_object_or_404
from .models import Producto, Categoria, Proveedor, Proyecto, Cliente, Almacen
from .forms import ProductoForm, CategoriaForm, ProveedorForm, ProyectoForm, ClienteForm, AlmacenForm
from django.contrib import messages

from django.db.models import Q
from django.db import IntegrityError
from django.views.decorators.http import require_POST

# Inicio Categorías

def categorias_list(request):
    categorias = Categoria.objects.all().order_by("nombre")
    return render(request, "catalogos/categorias_list.html", {
        "categorias": categorias,
    })


def categorias_create(request):
    if request.method == "POST":
        form = CategoriaForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect("categorias_list")
    else:
        form = CategoriaForm()

    return render(request, "catalogos/categorias_form.html", {
        "form": form,
        "modo_edicion": False,
    })


def categorias_edit(request, pk):
    categoria = get_object_or_404(Categoria, pk=pk)

    if request.method == "POST":
        form = CategoriaForm(request.POST, instance=categoria)
        if form.is_valid():
            form.save()
            return redirect("categorias_list")
    else:
        form = CategoriaForm(instance=categoria)

    return render(request, "catalogos/categorias_form.html", {
        "form": form,
        "modo_edicion": True,
        "categoria": categoria,
    })

# Fin Categorías

# Inicio Productos

def productos_list(request):
    productos = Producto.objects.all().order_by("nombre")
    return render(request, "catalogos/productos_list.html", {
        "productos": productos
    })

def productos_create(request):
    if request.method == "POST":
        form = ProductoForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            return redirect("productos_list")
    else:
        form = ProductoForm()

    return render(request, "catalogos/productos_form.html", {
        "form": form
    })

def productos_create_from_xml(request):
    idx = int(request.GET.get("i"))
    conceptos = request.session.get("ocf_xml_conceptos", [])

    if idx >= len(conceptos):
        messages.error(request, "Línea inválida.")
        return redirect("entrada_ocf_create")

    c = conceptos[idx]

    initial = {
        "nombre": c["descripcion_xml"],
        "clave_sat": c["clave_sat_xml"],
        "precio": c["valor_unitario_xml"],
    }

    if request.method == "POST":
        form = ProductoForm(request.POST, request.FILES)
        if form.is_valid():
            producto = form.save()

            # 🔑 Guardamos el producto creado para esa línea
            request.session["ocf_producto_creado"] = {
                "idx": idx,
                "producto_id": producto.id,
            }

            return redirect("entrada_ocf_create")

    else:
        form = ProductoForm(initial=initial)

    return render(request, "catalogos/productos_form.html", {
        "form": form,
        "desde_xml": True,
    })


def productos_edit(request, pk):
    producto = get_object_or_404(Producto, pk=pk)

    if request.method == "POST":
        form = ProductoForm(request.POST, request.FILES, instance=producto)
        if form.is_valid():
            form.save()
            return redirect("productos_list")
    else:
        form = ProductoForm(instance=producto)

    return render(request, "catalogos/productos_form.html", {
        "form": form,
        "producto": producto,
    })

def productos_delete(request, pk):
    producto = get_object_or_404(Producto, pk=pk)

    if producto.stock == 0:
        messages.error(request, f"No se puede eliminar un producto '{producto.nombre}' porque su stock es {producto.stock}.")
        return redirect("productos_list")

    if request.method == "POST":
        nombre = producto.nombre
        producto.delete()        
        messages.success(request, f"Producto '{nombre}' eliminado correctamente.")
        return redirect("productos_list")

    return render(request, "catalogos/productos_confirm_delete.html", {
        "producto": producto,        
    })


# Fin Productos


# Inicio Proveedores

def proveedores_list(request):
    proveedores = Proveedor.objects.all().order_by("nombre")
    return render(request, "catalogos/proveedores_list.html", {
        "proveedores": proveedores
    })

def proveedores_create(request):
    next_url = (request.GET.get("next") or "").strip()

    if request.method == "POST":
        form = ProveedorForm(request.POST)
        if form.is_valid():
            proveedor = form.save()
            messages.success(request, "Proveedor creado correctamente.")

            # ✅ Si venías de otra pantalla (ej. entrada manual), regresa y selecciona el proveedor
            if next_url:
                sep = "&" if "?" in next_url else "?"
                return redirect(f"{next_url}{sep}{urlencode({'proveedor_id': proveedor.id})}")

            return redirect("proveedores_list")
    else:
        form = ProveedorForm()

    return render(request, "catalogos/proveedores_form.html", {
        "form": form,
        "next": next_url,  # para que el template pueda usarlo en Cancelar
    })

def proveedores_edit(request, pk):
    proveedor = get_object_or_404(Proveedor, pk=pk)
    if request.method == "POST":
        form = ProveedorForm(request.POST, instance=proveedor)
        if form.is_valid():
            form.save()
            return redirect("proveedores_list")
    else:
        form = ProveedorForm(instance=proveedor)

    return render(request, "catalogos/proveedores_form.html", {
        "form": form,
        "proveedor": proveedor,
    })

# Fin Proveedores

# --- Proyectos ---

def proyectos_list(request):
    estado = request.GET.get("estado", "").strip()
    qs = Proyecto.objects.all().order_by("-fecha_actualizacion", "nombre")
    if estado:
        qs = qs.filter(estado=estado)

    return render(request, "catalogos/proyectos_list.html", {
        "proyectos": qs,
        "estado_actual": estado,
        "ESTADOS": Proyecto.Estado.choices,
    })


def proyectos_create(request):
    if request.method == "POST":
        form = ProyectoForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Proyecto creado correctamente.")
            return redirect("proyectos_list")
    else:
        form = ProyectoForm()

    return render(request, "catalogos/proyectos_form.html", {
        "form": form,
        "modo_edicion": False,
    })


def proyectos_edit(request, pk):
    proyecto = get_object_or_404(Proyecto, pk=pk)

    if request.method == "POST":
        form = ProyectoForm(request.POST, instance=proyecto)
        if form.is_valid():
            form.save()
            messages.success(request, "Proyecto actualizado correctamente.")
            return redirect("proyectos_list")
    else:
        form = ProyectoForm(instance=proyecto)

    return render(request, "catalogos/proyectos_form.html", {
        "form": form,
        "modo_edicion": True,
        "proyecto": proyecto,
    })

# --- Fin Proyectos ---

# --- Inicio Clientes ---

def clientes_list(request):
    q = (request.GET.get("q") or "").strip()

    clientes = Cliente.objects.all()
    if q:
        clientes = clientes.filter(
            Q(rfc__icontains=q) |
            Q(nombre_fiscal__icontains=q) |
            Q(nombre_comercial__icontains=q)
        )

    context = {
        "clientes": clientes,
        "q": q,
        "total": clientes.count(),
    }
    return render(request, "catalogos/clientes_list.html", context)


def cliente_create(request):
    if request.method == "POST":
        form = ClienteForm(request.POST)
        if form.is_valid():
            try:
                form.save()
                messages.success(request, "Cliente creado correctamente.")
                return redirect("clientes_list")
            except IntegrityError:
                # Por unique en RFC o nombre_normalizado (si aplica)
                form.add_error("rfc", "Ya existe un cliente con ese RFC.")
    else:
        form = ClienteForm()

    return render(request, "catalogos/cliente_form.html", {
        "form": form,
        "modo": "crear",
    })


def cliente_edit(request, pk):
    cliente = get_object_or_404(Cliente, pk=pk)

    if request.method == "POST":
        form = ClienteForm(request.POST, instance=cliente)
        if form.is_valid():
            try:
                form.save()
                messages.success(request, "Cliente actualizado correctamente.")
                return redirect("clientes_list")
            except IntegrityError:
                form.add_error("rfc", "Ya existe un cliente con ese RFC.")
    else:
        form = ClienteForm(instance=cliente)

    return render(request, "catalogos/cliente_form.html", {
        "form": form,
        "modo": "editar",
        "cliente": cliente,
    })


@require_POST
def cliente_quick_create(request):
    try:
        rfc = (request.POST.get("rfc") or "").strip().upper()
        nombre_fiscal = (request.POST.get("nombre_fiscal") or "").strip()
        regimen_fiscal = (request.POST.get("regimen_fiscal") or "").strip()
        domicilio_fiscal_cp = (request.POST.get("domicilio_fiscal_cp") or "").strip()

        telefono = (request.POST.get("telefono") or "").strip()
        email_cfdi = (request.POST.get("email_cfdi") or "").strip()

        if not (rfc and nombre_fiscal and regimen_fiscal and domicilio_fiscal_cp):
            return JsonResponse({"ok": False, "error": "Faltan campos requeridos."}, status=400)

        c = Cliente(
            rfc=rfc,
            nombre_fiscal=nombre_fiscal,
            regimen_fiscal=regimen_fiscal,
            domicilio_fiscal_cp=domicilio_fiscal_cp,
            telefono=telefono,
            email_cfdi=email_cfdi,
        )

        c.full_clean()
        c.save()

        return JsonResponse({
            "ok": True,
            "id": c.id,
            "rfc": c.rfc,
            "nombre_fiscal": c.nombre_fiscal,
        })

    except ValidationError as e:
        return JsonResponse({"ok": False, "error": "; ".join(sum(e.message_dict.values(), []))}, status=400)
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=400)


# --- Fin Clientes ---

# --- Almacenes ---

def almacenes_list(request):
    q = (request.GET.get("q") or "").strip()

    almacenes = Almacen.objects.all().order_by("nombre")
    if q:
        almacenes = almacenes.filter(
            Q(codigo__icontains=q) |
            Q(nombre__icontains=q) |
            Q(tipo__icontains=q)
        )

    return render(request, "catalogos/almacenes_list.html", {
        "almacenes": almacenes,
        "q": q,
        "total": almacenes.count(),
    })


def almacenes_create(request):
    if request.method == "POST":
        form = AlmacenForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Almacén creado correctamente.")
            return redirect("almacenes_list")
    else:
        form = AlmacenForm()

    return render(request, "catalogos/almacenes_form.html", {
        "form": form,
        "modo_edicion": False,
    })


def almacenes_edit(request, pk):
    almacen = get_object_or_404(Almacen, pk=pk)

    if request.method == "POST":
        form = AlmacenForm(request.POST, instance=almacen)
        if form.is_valid():
            form.save()
            messages.success(request, "Almacén actualizado correctamente.")
            return redirect("almacenes_list")
    else:
        form = AlmacenForm(instance=almacen)

    return render(request, "catalogos/almacenes_form.html", {
        "form": form,
        "modo_edicion": True,
        "almacen": almacen,
    })


def almacenes_confirm_delete(request, pk):
    almacen = get_object_or_404(Almacen, pk=pk)

    if request.method == "POST":
        nombre = str(almacen)
        almacen.delete()
        messages.success(request, f"Almacén '{nombre}' eliminado correctamente.")
        return redirect("almacenes_list")

    return render(request, "catalogos/almacenes_confirm_delete.html", {
        "almacen": almacen,
    })

# --- Fin Almacenes ---

# --- Inicio Importaciones ---

def _to_str(v):
    if v is None:
        return ""
    return str(v).strip()

def _to_bool_si_no(v, default=True):
    s = _to_str(v).upper()
    if s in ("SI", "S", "TRUE", "1", "X"):
        return True
    if s in ("NO", "N", "FALSE", "0"):
        return False
    return default

def _to_decimal(v, default=Decimal("0")):
    if v is None or str(v).strip() == "":
        return default
    try:
        return Decimal(str(v).strip())
    except (InvalidOperation, ValueError):
        return default

def _sheet_as_dict_rows(ws):
    """
    Lee la hoja usando encabezados en la fila 1.
    Devuelve lista de dicts: {header: value}.
    """
    headers = [(_to_str(c.value)) for c in ws[1]]
    rows = []
    for r in ws.iter_rows(min_row=2, values_only=True):
        row = {headers[i]: (r[i] if i < len(r) else None) for i in range(len(headers))}
        rows.append(row)
    return headers, rows

def importar_productos(request):
    if request.method == "POST" and request.FILES.get("archivo"):
        creados, actualizados, saltados = 0, 0, 0
        errores = []

        try:
            wb = load_workbook(request.FILES["archivo"], data_only=True)
            ws = wb.active
            headers, rows = _sheet_as_dict_rows(ws)

            # Esperados según tu template base
            # categoria, nombre, clave_sat, metrica, precio, stock, stock_minimo, stock_maximo, imagen, imagen_base64

            for idx, row in enumerate(rows, start=2):
                categoria_nombre = _to_str(row.get("categoria"))
                nombre = _to_str(row.get("nombre"))
                if not nombre:
                    saltados += 1
                    continue

                # categoria puede venir vacío porque en tu modelo es null=True/blank=True【turn2file2†models.py†L47-L54】
                categoria = None
                if categoria_nombre:
                    categoria, _ = Categoria.objects.get_or_create(nombre=categoria_nombre)

                data = {
                    "categoria": categoria,
                    "nombre": nombre,
                    "clave_sat": _to_str(row.get("clave_sat")) or None,
                    "metrica": _to_str(row.get("metrica")) or "PIEZA",
                    "precio": _to_decimal(row.get("precio")),
                    "stock": _to_decimal(row.get("stock")),
                    "stock_minimo": _to_decimal(row.get("stock_minimo")),
                    "stock_maximo": _to_decimal(row.get("stock_maximo")),
                    "imagen_base64": _to_str(row.get("imagen_base64")) or None,
                }

                # Nota: "imagen" (ImageField) no conviene importarla desde Excel directo (requiere archivo real).
                # Si quieres, luego hacemos una importación de imágenes por ZIP/rutas.

                try:
                    # En tu modelo, nombre_normalizado es unique, así que mejor update_or_create por nombre
                    obj, created = Producto.objects.update_or_create(
                        nombre=nombre,
                        defaults=data,
                    )
                    if created:
                        creados += 1
                    else:
                        actualizados += 1
                except Exception as e:
                    errores.append(f"Fila {idx}: {e}")

            if errores:
                messages.warning(
                    request,
                    f"Importación terminada. Creados: {creados}, Actualizados: {actualizados}, Saltados: {saltados}. "
                    f"Errores: {len(errores)} (ver consola)."
                )
                for err in errores[:20]:
                    print(err)
            else:
                messages.success(
                    request,
                    f"Importación terminada. Creados: {creados}, Actualizados: {actualizados}, Saltados: {saltados}."
                )

        except Exception as e:
            messages.error(request, f"Error al importar: {e}")

        return redirect("importar_productos")

    return render(request, "catalogos/importar_productos.html")

def importar_proveedores(request):
    if request.method == "POST" and request.FILES.get("archivo"):
        creados, actualizados, saltados = 0, 0, 0
        errores = []

        try:
            wb = load_workbook(request.FILES["archivo"], data_only=True)
            ws = wb.active
            headers, rows = _sheet_as_dict_rows(ws)

            for idx, row in enumerate(rows, start=2):
                nombre = _to_str(row.get("nombre"))
                if not nombre:
                    saltados += 1
                    continue

                data = {
                    "nombre": nombre,
                    "rfc": _to_str(row.get("rfc")) or None,
                    "contacto": _to_str(row.get("contacto")) or None,
                    "telefono": _to_str(row.get("telefono")) or None,
                    "email": _to_str(row.get("email")) or None,
                    "direccion": _to_str(row.get("direccion")) or None,
                    "activo": _to_bool_si_no(row.get("activo"), default=True),
                }

                try:
                    # nombre_normalizado es unique => update_or_create por nombre
                    obj, created = Proveedor.objects.update_or_create(
                        nombre=nombre,
                        defaults=data,
                    )
                    if created:
                        creados += 1
                    else:
                        actualizados += 1
                except Exception as e:
                    errores.append(f"Fila {idx}: {e}")

            if errores:
                messages.warning(
                    request,
                    f"Importación terminada. Creados: {creados}, Actualizados: {actualizados}, Saltados: {saltados}. "
                    f"Errores: {len(errores)} (ver consola)."
                )
                for err in errores[:20]:
                    print(err)
            else:
                messages.success(
                    request,
                    f"Importación terminada. Creados: {creados}, Actualizados: {actualizados}, Saltados: {saltados}."
                )

        except Exception as e:
            messages.error(request, f"Error al importar: {e}")

        return redirect("importar_proveedores")

    return render(request, "catalogos/importar_proveedores.html")


def importar_clientes(request):
    if request.method == "POST" and request.FILES.get("archivo"):
        creados, actualizados, saltados = 0, 0, 0
        errores = []

        try:
            wb = load_workbook(request.FILES["archivo"], data_only=True)
            ws = wb.active
            headers, rows = _sheet_as_dict_rows(ws)

            for idx, row in enumerate(rows, start=2):
                # Campos clave / obligatorios
                rfc = _to_str(row.get("rfc")).upper()
                nombre_fiscal = _to_str(row.get("nombre_fiscal"))
                regimen_fiscal = _to_str(row.get("regimen_fiscal"))
                domicilio_fiscal_cp = _to_str(row.get("domicilio_fiscal_cp"))

                # si falta algo obligatorio, se salta y lo reporta
                if not rfc or not nombre_fiscal or not regimen_fiscal or not domicilio_fiscal_cp:
                    saltados += 1
                    continue

                data = {
                    "tipo_persona": _to_str(row.get("tipo_persona")) or Cliente.TipoPersona.MORAL,
                    "rfc": rfc,
                    "nombre_fiscal": nombre_fiscal,
                    "regimen_fiscal": regimen_fiscal,
                    "domicilio_fiscal_cp": domicilio_fiscal_cp,

                    "uso_cfdi_default": _to_str(row.get("uso_cfdi_default")),
                    "email_cfdi": _to_str(row.get("email_cfdi")),
                    "nombre_comercial": _to_str(row.get("nombre_comercial")),
                    "telefono": _to_str(row.get("telefono")),

                    "calle": _to_str(row.get("calle")),
                    "num_ext": _to_str(row.get("num_ext")),
                    "num_int": _to_str(row.get("num_int")),
                    "colonia": _to_str(row.get("colonia")),
                    "localidad": _to_str(row.get("localidad")),
                    "municipio": _to_str(row.get("municipio")),
                    "estado": _to_str(row.get("estado")),
                    "pais": _to_str(row.get("pais")) or "México",
                    "cp": _to_str(row.get("cp")),
                    "referencias": _to_str(row.get("referencias")),

                    "forma_pago_default": _to_str(row.get("forma_pago_default")),
                    "metodo_pago_default": _to_str(row.get("metodo_pago_default")),
                    "activo": _to_bool_si_no(row.get("activo"), default=True),
                }

                try:
                    obj, created = Cliente.objects.update_or_create(
                        rfc=rfc,  # es unique【turn2file0†models.py†L34-L44】
                        defaults=data,
                    )
                    if created:
                        creados += 1
                    else:
                        actualizados += 1
                except Exception as e:
                    errores.append(f"Fila {idx} (RFC {rfc}): {e}")

            if errores:
                messages.warning(
                    request,
                    f"Importación terminada. Creados: {creados}, Actualizados: {actualizados}, Saltados: {saltados}. "
                    f"Errores: {len(errores)} (ver consola)."
                )
                for err in errores[:30]:
                    print(err)
            else:
                messages.success(
                    request,
                    f"Importación terminada. Creados: {creados}, Actualizados: {actualizados}, Saltados: {saltados}."
                )

        except Exception as e:
            messages.error(request, f"Error al importar: {e}")

        return redirect("importar_clientes")

    return render(request, "catalogos/importar_clientes.html")

# --- Fin Importaciones ---