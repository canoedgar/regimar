from decimal import Decimal

from django.apps import apps
from django.db import transaction


# ============================================================
# CONFIGURACIÓN DE SEGURIDAD
# ============================================================

# Cambia a True solo cuando estés seguro.
CONFIRMAR_LIMPIEZA = True

# Limpia movimientos de cartera antes de borrar salidas/notas de venta.
# Recomendado en True si ya existe el módulo cartera.
LIMPIAR_CARTERA = True

# Si ya implementaste bitácora de precios y también quieres limpiarla,
# cambia esto a True.
LIMPIAR_BITACORA_PRECIOS = True

# Si quieres conservar los registros de InventarioStock pero en cero,
# deja esto en False.
# Si prefieres borrar completamente las filas de stock por almacén,
# cambia a True.
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


def eliminar_queryset(modelo, descripcion):
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


# ============================================================
# LIMPIEZA DE CARTERA
# ============================================================

def limpiar_cartera():
    """
    Limpia registros financieros del módulo cartera.

    Orden recomendado:
    1. Movimientos de saldo a favor.
    2. Aplicaciones de pagos a notas.
    3. Detalles de métodos de pago.
    4. Pagos de clientes.

    Esto evita conflictos con relaciones PROTECT hacia notas de venta.
    """
    if not LIMPIAR_CARTERA:
        print("Limpieza de cartera desactivada.")
        return

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
        return

    print("=" * 70)
    print("INICIANDO LIMPIEZA DE CARTERA")
    print("=" * 70)

    print(f"Pagos de clientes: {contar_modelo(PagoCliente)}")
    print(f"Métodos de pago: {contar_modelo(PagoMetodoDetalle)}")
    print(f"Aplicaciones a notas: {contar_modelo(PagoAplicacionNota)}")
    print(f"Movimientos saldo a favor: {contar_modelo(ClienteSaldoFavorMovimiento)}")
    print("-" * 70)

    # Primero borrar movimientos que dependen de pagos/notas.
    eliminar_queryset(
        ClienteSaldoFavorMovimiento,
        "Movimientos de saldo a favor",
    )

    eliminar_queryset(
        PagoAplicacionNota,
        "Aplicaciones de pago a notas",
    )

    eliminar_queryset(
        PagoMetodoDetalle,
        "Métodos de pago",
    )

    eliminar_queryset(
        PagoCliente,
        "Pagos de clientes",
    )

    print("=" * 70)
    print("CARTERA LIMPIA")
    print("=" * 70)


# ============================================================
# LIMPIEZA DE INVENTARIO
# ============================================================

def limpiar_inventario():
    if not CONFIRMAR_LIMPIEZA:
        print("=" * 70)
        print("LIMPIEZA CANCELADA POR SEGURIDAD")
        print("=" * 70)
        print("Para ejecutar la limpieza cambia:")
        print("")
        print("CONFIRMAR_LIMPIEZA = True")
        print("")
        print("Este proceso eliminará cartera, entradas, salidas y reiniciará stock.")
        print("Haz respaldo de la base de datos antes de ejecutarlo.")
        print("=" * 70)
        return

    EntradaInventario = modelo_existe("inventarios", "EntradaInventario")
    SalidaInventario = modelo_existe("inventarios", "SalidaInventario")
    InventarioStock = modelo_existe("inventarios", "InventarioStock")
    Producto = modelo_existe("catalogos", "Producto")

    ProductoPrecioBitacora = modelo_existe("catalogos", "ProductoPrecioBitacora")
    ProductoPrecioHistorial = modelo_existe("catalogos", "ProductoPrecioHistorial")

    if not EntradaInventario or not SalidaInventario or not InventarioStock or not Producto:
        print("=" * 70)
        print("ERROR: NO SE ENCONTRARON TODOS LOS MODELOS REQUERIDOS")
        print("=" * 70)
        print(f"EntradaInventario: {'OK' if EntradaInventario else 'NO EXISTE'}")
        print(f"SalidaInventario: {'OK' if SalidaInventario else 'NO EXISTE'}")
        print(f"InventarioStock: {'OK' if InventarioStock else 'NO EXISTE'}")
        print(f"Producto: {'OK' if Producto else 'NO EXISTE'}")
        print("=" * 70)
        return

    print("=" * 70)
    print("INICIANDO LIMPIEZA GENERAL")
    print("=" * 70)
    print("ADVERTENCIA:")
    print("- Se limpiará cartera si LIMPIAR_CARTERA = True.")
    print("- Se eliminarán salidas/notas de venta.")
    print("- Se eliminarán entradas de inventario.")
    print("- Se reiniciará o eliminará stock.")
    print("- Se conservarán productos, clientes, proveedores, almacenes y catálogos.")
    print("=" * 70)

    with transaction.atomic():
        total_entradas = EntradaInventario.objects.count()
        total_salidas = SalidaInventario.objects.count()
        total_stocks = InventarioStock.objects.count()
        total_productos = Producto.objects.count()

        print(f"Entradas a eliminar: {total_entradas}")
        print(f"Salidas a eliminar: {total_salidas}")
        print(f"Registros de stock: {total_stocks}")
        print(f"Productos a reiniciar: {total_productos}")
        print("-" * 70)

        # 0. Limpiar cartera primero.
        # Importante: cartera puede tener ForeignKey con PROTECT hacia SalidaInventario.
        limpiar_cartera()

        # 1. Eliminar salidas.
        # Esto elimina por cascada:
        # - SalidaInventarioDetalle
        # - SalidaInventarioDetalleAlmacen
        salidas_eliminadas, detalle_salidas = SalidaInventario.objects.all().delete()
        print(f"Salidas eliminadas: {salidas_eliminadas}")
        print(f"Detalle eliminación salidas: {detalle_salidas}")

        # 2. Eliminar entradas.
        # Esto elimina por cascada:
        # - EntradaInventarioDetalle
        entradas_eliminadas, detalle_entradas = EntradaInventario.objects.all().delete()
        print(f"Entradas eliminadas: {entradas_eliminadas}")
        print(f"Detalle eliminación entradas: {detalle_entradas}")

        # 3. Limpiar stock por almacén.
        if BORRAR_FILAS_STOCK:
            stocks_eliminados, detalle_stocks = InventarioStock.objects.all().delete()
            print(f"Filas de InventarioStock eliminadas: {stocks_eliminados}")
            print(f"Detalle eliminación stock: {detalle_stocks}")
        else:
            campos_stock = {}

            if campo_existe(InventarioStock, "cantidad"):
                campos_stock["cantidad"] = Decimal("0")

            if campo_existe(InventarioStock, "costo_promedio"):
                campos_stock["costo_promedio"] = Decimal("0")

            if campo_existe(InventarioStock, "stock"):
                campos_stock["stock"] = Decimal("0")

            if campos_stock:
                InventarioStock.objects.all().update(**campos_stock)
                print("InventarioStock reiniciado en cero.")
            else:
                print("InventarioStock no tiene campos conocidos para reiniciar; se omite update.")

        # 4. Reiniciar stock global del producto.
        campos_producto = {}

        if campo_existe(Producto, "stock"):
            campos_producto["stock"] = Decimal("0")

        # Campos opcionales si ya aplicaste el modelo de costos/precios.
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

        if campos_producto:
            Producto.objects.all().update(**campos_producto)
            print("Stock, costos y precios de Producto reiniciados.")
        else:
            print("Producto no tiene campos conocidos para reiniciar; se omite update.")

        # 5. Opcional: limpiar bitácoras de precios.
        if LIMPIAR_BITACORA_PRECIOS:
            eliminar_queryset(
                ProductoPrecioBitacora,
                "Bitácora diaria de precios",
            )

            eliminar_queryset(
                ProductoPrecioHistorial,
                "Historial de precios",
            )

    print("=" * 70)
    print("LIMPIEZA FINALIZADA CORRECTAMENTE")
    print("=" * 70)
    print("Cartera limpia." if LIMPIAR_CARTERA else "Cartera conservada.")
    print("Inventario limpio.")
    print("Productos conservados.")
    print("Proveedores, clientes, almacenes y catálogos conservados.")
    print("=" * 70)


limpiar_inventario()