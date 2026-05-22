from decimal import Decimal

from django.apps import apps
from django.db import transaction


# ============================================================
# CONFIGURACIÓN DE SEGURIDAD
# ============================================================

# Cambia a True solo cuando estés seguro.
CONFIRMAR_LIMPIEZA = True

# Si ya implementaste bitácora de precios y también quieres limpiarla,
# cambia esto a True.
LIMPIAR_BITACORA_PRECIOS = True

# Si quieres conservar los registros de InventarioStock pero en cero,
# deja esto en False.
# Si prefieres borrar completamente las filas de stock por almacén,
# cambia a True.
BORRAR_FILAS_STOCK = True


def modelo_existe(app_label, model_name):
    try:
        return apps.get_model(app_label, model_name)
    except LookupError:
        return None


def campo_existe(modelo, campo):
    return any(f.name == campo for f in modelo._meta.fields)


def limpiar_inventario():
    if not CONFIRMAR_LIMPIEZA:
        print("=" * 70)
        print("LIMPIEZA CANCELADA POR SEGURIDAD")
        print("=" * 70)
        print("Para ejecutar la limpieza cambia:")
        print("")
        print("CONFIRMAR_LIMPIEZA = True")
        print("")
        print("Este proceso eliminará entradas, salidas y reiniciará stock.")
        print("Haz respaldo de la base de datos antes de ejecutarlo.")
        print("=" * 70)
        return

    EntradaInventario = apps.get_model("inventarios", "EntradaInventario")
    SalidaInventario = apps.get_model("inventarios", "SalidaInventario")
    InventarioStock = apps.get_model("inventarios", "InventarioStock")
    Producto = apps.get_model("catalogos", "Producto")

    ProductoPrecioBitacora = modelo_existe("catalogos", "ProductoPrecioBitacora")
    ProductoPrecioHistorial = modelo_existe("catalogos", "ProductoPrecioHistorial")

    print("=" * 70)
    print("INICIANDO LIMPIEZA DE INVENTARIO")
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
            campos_stock = {"cantidad": Decimal("0")}

            if campo_existe(InventarioStock, "costo_promedio"):
                campos_stock["costo_promedio"] = Decimal("0")

            InventarioStock.objects.all().update(**campos_stock)
            print("InventarioStock reiniciado en cero.")

        # 4. Reiniciar stock global del producto.
        campos_producto = {
            "stock": Decimal("0"),
        }

        # Campos opcionales si ya aplicaste el modelo de precios.
        if campo_existe(Producto, "costo_promedio"):
            campos_producto["costo_promedio"] = Decimal("0")

        if campo_existe(Producto, "ultimo_costo_compra"):
            campos_producto["ultimo_costo_compra"] = Decimal("0")

        if campo_existe(Producto, "fecha_ultima_compra"):
            campos_producto["fecha_ultima_compra"] = None

        Producto.objects.all().update(**campos_producto)
        print("Stock y costos de Producto reiniciados.")

        # 5. Opcional: limpiar bitácoras de precios.
        if LIMPIAR_BITACORA_PRECIOS:
            if ProductoPrecioBitacora:
                bitacoras_eliminadas, detalle_bitacoras = ProductoPrecioBitacora.objects.all().delete()
                print(f"Bitácora diaria de precios eliminada: {bitacoras_eliminadas}")
                print(f"Detalle bitácora diaria: {detalle_bitacoras}")

            if ProductoPrecioHistorial:
                historiales_eliminados, detalle_historiales = ProductoPrecioHistorial.objects.all().delete()
                print(f"Historial de precios eliminado: {historiales_eliminados}")
                print(f"Detalle historial precios: {detalle_historiales}")

    print("=" * 70)
    print("LIMPIEZA FINALIZADA CORRECTAMENTE")
    print("=" * 70)
    print("Inventario limpio.")
    print("Productos conservados.")
    print("Proveedores, clientes, almacenes y catálogos conservados.")
    print("=" * 70)


limpiar_inventario()