from decimal import Decimal

from django.apps import apps
from django.db import transaction
from django.db.models.deletion import ProtectedError


# ============================================================
# CONFIGURACIÓN DE SEGURIDAD
# ============================================================

# Interruptor general. Déjalo en False cuando no se quiera permitir
# ninguna limpieza, aunque el usuario confirme en consola.
CONFIRMAR_LIMPIEZA = True

# Texto que se debe escribir para aprobar cada limpieza.
# Se pide por cada sección para reducir el riesgo de borrados accidentales.
TEXTO_CONFIRMACION = "SI"

# Limpieza de módulos / secciones.
LIMPIAR_CARTERA = True
LIMPIAR_COTIZACIONES = True
LIMPIAR_INVENTARIO = True
LIMPIAR_BITACORA_PRECIOS = True

# Si quieres conservar los registros de InventarioStock pero en cero,
# deja esto en False. Si prefieres borrar completamente las filas de stock
# por almacén, cambia a True.
BORRAR_FILAS_STOCK = True


# ============================================================
# HELPERS
# ============================================================

def modelo_existe(app_label, model_name):
    """
    Regresa el modelo si existe; en caso contrario regresa None.
    Esto permite que el script funcione aunque algunos módulos/modelos
    todavía no estén implementados en el proyecto.
    """
    try:
        return apps.get_model(app_label, model_name)
    except LookupError:
        return None


def campo_existe(modelo, campo):
    """
    Valida si un campo existe en el modelo.
    Soporta campos normales y relaciones.
    """
    if not modelo:
        return False

    return any(f.name == campo for f in modelo._meta.get_fields())


def contar_modelo(modelo):
    if not modelo:
        return 0
    return modelo.objects.count()


def imprimir_titulo(titulo):
    print("=" * 70)
    print(titulo)
    print("=" * 70)


def imprimir_separador():
    print("-" * 70)


def confirmar_accion(nombre_limpieza, resumen):
    """
    Solicita confirmación explícita para una sección de limpieza.
    Solo regresa True si el usuario escribe exactamente el valor de
    TEXTO_CONFIRMACION.
    """
    imprimir_titulo(f"CONFIRMACIÓN REQUERIDA: {nombre_limpieza}")

    for linea in resumen:
        print(linea)

    imprimir_separador()
    print(f"Para ejecutar esta sección escribe exactamente: {TEXTO_CONFIRMACION}")
    respuesta = input("Confirmación: ").strip()

    if respuesta == TEXTO_CONFIRMACION:
        print(f"{nombre_limpieza}: confirmada.")
        imprimir_separador()
        return True

    print(f"{nombre_limpieza}: omitida por falta de confirmación.")
    imprimir_separador()
    return False


def eliminar_modelo(modelo, descripcion):
    """
    Elimina todos los registros de un modelo si existe.
    Imprime detalle de la eliminación.
    """
    if not modelo:
        print(f"{descripcion}: modelo no existe, se omite.")
        return 0, {}

    total = modelo.objects.count()

    if total == 0:
        print(f"{descripcion}: sin registros.")
        return 0, {}

    eliminados, detalle = modelo.objects.all().delete()
    print(f"{descripcion} eliminados: {eliminados}")
    print(f"Detalle {descripcion}: {detalle}")
    return eliminados, detalle


def actualizar_modelo(modelo, descripcion, **campos):
    """
    Actualiza todos los registros de un modelo si existe y hay campos válidos.
    """
    if not modelo:
        print(f"{descripcion}: modelo no existe, se omite.")
        return 0

    if not campos:
        print(f"{descripcion}: no hay campos válidos para actualizar; se omite.")
        return 0

    total = modelo.objects.count()

    if total == 0:
        print(f"{descripcion}: sin registros.")
        return 0

    actualizados = modelo.objects.all().update(**campos)
    print(f"{descripcion} actualizados: {actualizados}")
    return actualizados


def ejecutar_seccion(nombre_limpieza, resumen, funcion_limpieza):
    """
    Pide confirmación y ejecuta una sección dentro de una transacción corta.
    Así no se mantiene una transacción abierta mientras el usuario decide.
    """
    if not confirmar_accion(nombre_limpieza, resumen):
        return False

    try:
        with transaction.atomic():
            funcion_limpieza()
    except ProtectedError as exc:
        imprimir_titulo(f"ERROR EN {nombre_limpieza}")
        print("No se pudo completar la limpieza porque existen registros protegidos por relaciones.")
        print("Detalle técnico:")
        print(exc)
        imprimir_separador()
        print("Revisa el orden de limpieza o confirma primero las secciones dependientes.")
        return False

    return True


# ============================================================
# LIMPIEZA DE CARTERA
# ============================================================

def limpiar_cartera():
    """
    Limpia registros financieros del módulo cartera.

    Orden:
    1. Movimientos de saldo a favor.
    2. Aplicaciones de pagos a notas.
    3. Detalles de métodos de pago.
    4. Pagos de clientes.

    Esto evita conflictos con relaciones PROTECT hacia notas de venta.
    """
    if not LIMPIAR_CARTERA:
        print("Limpieza de cartera desactivada.")
        return False

    PagoCliente = modelo_existe("cartera", "PagoCliente")
    PagoMetodoDetalle = modelo_existe("cartera", "PagoMetodoDetalle")
    PagoAplicacionNota = modelo_existe("cartera", "PagoAplicacionNota")
    ClienteSaldoFavorMovimiento = modelo_existe("cartera", "ClienteSaldoFavorMovimiento")

    modelos_cartera = [
        PagoCliente,
        PagoMetodoDetalle,
        PagoAplicacionNota,
        ClienteSaldoFavorMovimiento,
    ]

    if not any(modelos_cartera):
        print("Módulo cartera no encontrado o sin modelos esperados. Se omite limpieza de cartera.")
        return False

    resumen = [
        f"Pagos de clientes a eliminar: {contar_modelo(PagoCliente)}",
        f"Métodos de pago a eliminar: {contar_modelo(PagoMetodoDetalle)}",
        f"Aplicaciones de pago a notas a eliminar: {contar_modelo(PagoAplicacionNota)}",
        f"Movimientos de saldo a favor a eliminar: {contar_modelo(ClienteSaldoFavorMovimiento)}",
    ]

    def _ejecutar():
        imprimir_titulo("INICIANDO LIMPIEZA DE CARTERA")
        eliminar_modelo(ClienteSaldoFavorMovimiento, "Movimientos de saldo a favor")
        eliminar_modelo(PagoAplicacionNota, "Aplicaciones de pago a notas")
        eliminar_modelo(PagoMetodoDetalle, "Métodos de pago")
        eliminar_modelo(PagoCliente, "Pagos de clientes")
        imprimir_titulo("CARTERA LIMPIA")

    return ejecutar_seccion("LIMPIEZA DE CARTERA", resumen, _ejecutar)


# ============================================================
# LIMPIEZA DE COTIZACIONES
# ============================================================

def limpiar_cotizaciones():
    """
    Limpia cotizaciones y sus detalles.
    No afecta clientes, productos ni precios base del catálogo.
    """
    if not LIMPIAR_COTIZACIONES:
        print("Limpieza de cotizaciones desactivada.")
        return False

    CotizacionPrecio = modelo_existe("cotizaciones", "CotizacionPrecio")
    CotizacionPrecioDetalle = modelo_existe("cotizaciones", "CotizacionPrecioDetalle")

    modelos_cotizaciones = [CotizacionPrecio, CotizacionPrecioDetalle]

    if not any(modelos_cotizaciones):
        print("Módulo cotizaciones no encontrado o sin modelos esperados. Se omite limpieza de cotizaciones.")
        return False

    resumen = [
        f"Cotizaciones a eliminar: {contar_modelo(CotizacionPrecio)}",
        f"Detalles de cotización a eliminar: {contar_modelo(CotizacionPrecioDetalle)}",
    ]

    def _ejecutar():
        imprimir_titulo("INICIANDO LIMPIEZA DE COTIZACIONES")
        # Se eliminan primero los detalles para dejar claro el orden y evitar residuos.
        eliminar_modelo(CotizacionPrecioDetalle, "Detalles de cotización")
        eliminar_modelo(CotizacionPrecio, "Cotizaciones")
        imprimir_titulo("COTIZACIONES LIMPIAS")

    return ejecutar_seccion("LIMPIEZA DE COTIZACIONES", resumen, _ejecutar)


# ============================================================
# LIMPIEZA DE SALIDAS / NOTAS DE VENTA
# ============================================================

def limpiar_salidas():
    SalidaInventario = modelo_existe("inventarios", "SalidaInventario")
    SalidaInventarioDetalle = modelo_existe("inventarios", "SalidaInventarioDetalle")
    SalidaInventarioDetalleAlmacen = modelo_existe("inventarios", "SalidaInventarioDetalleAlmacen")

    if not SalidaInventario:
        print("SalidaInventario no existe. Se omite limpieza de salidas.")
        return False

    resumen = [
        f"Salidas / notas de venta a eliminar: {contar_modelo(SalidaInventario)}",
        f"Detalles de salida a eliminar por cascada: {contar_modelo(SalidaInventarioDetalle)}",
        f"Detalles por almacén a eliminar por cascada: {contar_modelo(SalidaInventarioDetalleAlmacen)}",
        "Nota: si cartera no fue limpiada primero, esta sección puede fallar por relaciones protegidas.",
    ]

    def _ejecutar():
        imprimir_titulo("INICIANDO LIMPIEZA DE SALIDAS / NOTAS DE VENTA")
        eliminar_modelo(SalidaInventario, "Salidas / notas de venta")
        imprimir_titulo("SALIDAS / NOTAS DE VENTA LIMPIAS")

    return ejecutar_seccion("LIMPIEZA DE SALIDAS / NOTAS DE VENTA", resumen, _ejecutar)


# ============================================================
# LIMPIEZA DE ENTRADAS DE INVENTARIO
# ============================================================

def limpiar_entradas():
    EntradaInventario = modelo_existe("inventarios", "EntradaInventario")
    EntradaInventarioDetalle = modelo_existe("inventarios", "EntradaInventarioDetalle")

    if not EntradaInventario:
        print("EntradaInventario no existe. Se omite limpieza de entradas.")
        return False

    resumen = [
        f"Entradas de inventario a eliminar: {contar_modelo(EntradaInventario)}",
        f"Detalles de entrada a eliminar por cascada: {contar_modelo(EntradaInventarioDetalle)}",
    ]

    def _ejecutar():
        imprimir_titulo("INICIANDO LIMPIEZA DE ENTRADAS DE INVENTARIO")
        eliminar_modelo(EntradaInventario, "Entradas de inventario")
        imprimir_titulo("ENTRADAS DE INVENTARIO LIMPIAS")

    return ejecutar_seccion("LIMPIEZA DE ENTRADAS DE INVENTARIO", resumen, _ejecutar)


# ============================================================
# LIMPIEZA / REINICIO DE STOCK
# ============================================================

def limpiar_stock():
    InventarioStock = modelo_existe("inventarios", "InventarioStock")

    if not InventarioStock:
        print("InventarioStock no existe. Se omite limpieza de stock.")
        return False

    accion = "eliminar" if BORRAR_FILAS_STOCK else "reiniciar en cero"
    resumen = [
        f"Registros de InventarioStock a {accion}: {contar_modelo(InventarioStock)}",
    ]

    def _ejecutar():
        imprimir_titulo("INICIANDO LIMPIEZA / REINICIO DE STOCK POR ALMACÉN")

        if BORRAR_FILAS_STOCK:
            eliminar_modelo(InventarioStock, "Filas de InventarioStock")
        else:
            campos_stock = {}

            if campo_existe(InventarioStock, "cantidad"):
                campos_stock["cantidad"] = Decimal("0")

            if campo_existe(InventarioStock, "costo_promedio"):
                campos_stock["costo_promedio"] = Decimal("0")

            if campo_existe(InventarioStock, "stock"):
                campos_stock["stock"] = Decimal("0")

            actualizar_modelo(InventarioStock, "InventarioStock", **campos_stock)

        imprimir_titulo("STOCK POR ALMACÉN LIMPIO")

    return ejecutar_seccion("LIMPIEZA / REINICIO DE STOCK POR ALMACÉN", resumen, _ejecutar)


# ============================================================
# REINICIO DE PRODUCTOS
# ============================================================

def reiniciar_productos():
    Producto = modelo_existe("catalogos", "Producto")

    if not Producto:
        print("Producto no existe. Se omite reinicio de productos.")
        return False

    campos_producto = {}

    if campo_existe(Producto, "stock"):
        campos_producto["stock"] = Decimal("0")

    if campo_existe(Producto, "costo_promedio"):
        campos_producto["costo_promedio"] = Decimal("0")

    if campo_existe(Producto, "ultimo_costo_compra"):
        campos_producto["ultimo_costo_compra"] = Decimal("0")

    if campo_existe(Producto, "fecha_ultima_compra"):
        campos_producto["fecha_ultima_compra"] = None

    if campo_existe(Producto, "precio"):
        campos_producto["precio"] = Decimal("0")

    if campo_existe(Producto, "precio_minimo"):
        campos_producto["precio_minimo"] = Decimal("0")

    if not campos_producto:
        print("Producto no tiene campos conocidos para reiniciar; se omite reinicio de productos.")
        return False

    resumen = [
        f"Productos a actualizar/reiniciar: {contar_modelo(Producto)}",
        "Campos a reiniciar: " + ", ".join(campos_producto.keys()),
        "Nota: los productos no se eliminan; solo se reinician stock/costos/precios detectados.",
    ]

    def _ejecutar():
        imprimir_titulo("INICIANDO REINICIO DE PRODUCTOS")
        actualizar_modelo(Producto, "Productos", **campos_producto)
        imprimir_titulo("PRODUCTOS REINICIADOS")

    return ejecutar_seccion("REINICIO DE PRODUCTOS", resumen, _ejecutar)


# ============================================================
# LIMPIEZA DE BITÁCORAS DE PRECIOS
# ============================================================

def limpiar_bitacoras_precios():
    if not LIMPIAR_BITACORA_PRECIOS:
        print("Limpieza de bitácoras de precios desactivada.")
        return False

    ProductoPrecioBitacora = modelo_existe("catalogos", "ProductoPrecioBitacora")
    ProductoPrecioHistorial = modelo_existe("catalogos", "ProductoPrecioHistorial")

    modelos_bitacora = [ProductoPrecioBitacora, ProductoPrecioHistorial]

    if not any(modelos_bitacora):
        print("No se encontraron modelos de bitácora/historial de precios. Se omite limpieza.")
        return False

    resumen = [
        f"Registros de bitácora diaria de precios a eliminar: {contar_modelo(ProductoPrecioBitacora)}",
        f"Registros de historial de precios a eliminar: {contar_modelo(ProductoPrecioHistorial)}",
    ]

    def _ejecutar():
        imprimir_titulo("INICIANDO LIMPIEZA DE BITÁCORAS DE PRECIOS")
        eliminar_modelo(ProductoPrecioBitacora, "Bitácora diaria de precios")
        eliminar_modelo(ProductoPrecioHistorial, "Historial de precios")
        imprimir_titulo("BITÁCORAS DE PRECIOS LIMPIAS")

    return ejecutar_seccion("LIMPIEZA DE BITÁCORAS DE PRECIOS", resumen, _ejecutar)


# ============================================================
# ORQUESTADOR GENERAL
# ============================================================

def validar_modelos_base():
    EntradaInventario = modelo_existe("inventarios", "EntradaInventario")
    SalidaInventario = modelo_existe("inventarios", "SalidaInventario")
    InventarioStock = modelo_existe("inventarios", "InventarioStock")
    Producto = modelo_existe("catalogos", "Producto")

    if not EntradaInventario or not SalidaInventario or not InventarioStock or not Producto:
        imprimir_titulo("ERROR: NO SE ENCONTRARON TODOS LOS MODELOS BASE REQUERIDOS")
        print(f"EntradaInventario: {'OK' if EntradaInventario else 'NO EXISTE'}")
        print(f"SalidaInventario: {'OK' if SalidaInventario else 'NO EXISTE'}")
        print(f"InventarioStock: {'OK' if InventarioStock else 'NO EXISTE'}")
        print(f"Producto: {'OK' if Producto else 'NO EXISTE'}")
        imprimir_titulo("PROCESO CANCELADO")
        return False

    return True


def limpiar_sistema():
    if not CONFIRMAR_LIMPIEZA:
        imprimir_titulo("LIMPIEZA CANCELADA POR SEGURIDAD")
        print("Para permitir la ejecución cambia:")
        print("")
        print("CONFIRMAR_LIMPIEZA = True")
        print("")
        print("Haz respaldo de la base de datos antes de ejecutar este proceso.")
        imprimir_titulo("PROCESO CANCELADO")
        return

    if LIMPIAR_INVENTARIO and not validar_modelos_base():
        return

    imprimir_titulo("LIMPIEZA SEGURA DEL SISTEMA")
    print("ADVERTENCIA:")
    print("- Este proceso puede eliminar cartera, cotizaciones, salidas/notas de venta y entradas.")
    print("- También puede eliminar o reiniciar stock y reiniciar datos de productos.")
    print("- Productos, clientes, proveedores, almacenes y catálogos se conservan.")
    print("- Antes de cada sección se mostrará el conteo y se pedirá confirmación.")
    imprimir_separador()
    print(f"Texto requerido para confirmar cada sección: {TEXTO_CONFIRMACION}")
    imprimir_titulo("INICIO")

    resultados = []

    # Orden seguro para evitar relaciones protegidas:
    # cartera -> cotizaciones -> salidas -> entradas -> stock -> productos -> bitácoras.
    if LIMPIAR_CARTERA:
        resultados.append(("Cartera", limpiar_cartera()))

    if LIMPIAR_COTIZACIONES:
        resultados.append(("Cotizaciones", limpiar_cotizaciones()))

    if LIMPIAR_INVENTARIO:
        resultados.append(("Salidas / notas de venta", limpiar_salidas()))
        resultados.append(("Entradas de inventario", limpiar_entradas()))
        resultados.append(("Stock por almacén", limpiar_stock()))
        resultados.append(("Productos", reiniciar_productos()))

    if LIMPIAR_BITACORA_PRECIOS:
        resultados.append(("Bitácoras de precios", limpiar_bitacoras_precios()))

    imprimir_titulo("RESUMEN FINAL")
    for nombre, ejecutado in resultados:
        estado = "EJECUTADA" if ejecutado else "OMITIDA / NO COMPLETADA"
        print(f"{nombre}: {estado}")

    imprimir_separador()
    print("Proceso terminado.")
    print("Recomendación: valida reportes de inventario, cartera y cotizaciones antes de continuar operando.")
    imprimir_titulo("FIN")


limpiar_sistema()
