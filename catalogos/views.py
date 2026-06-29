# catalogos/views.py
"""Fachada de compatibilidad para vistas de catalogos.

Las implementaciones viven en modulos separados por subdominio para mantener
`catalogos.urls` e imports historicos sin cambios durante la transicion.
"""

from catalogos.views_categorias import (
    categorias_create,
    categorias_edit,
    categorias_list,
)
from catalogos.views_productos import (
    parametros_sistema_create,
    parametros_sistema_edit,
    parametros_sistema_list,
    precio_cliente_edit,
    precios_clientes_list,
    precios_productos_list,
    producto_precio_bitacora,
    productos_create,
    productos_delete,
    productos_edit,
    productos_list,
)
from catalogos.views_proveedores import (
    proveedores_create,
    proveedores_edit,
    proveedores_list,
)
from catalogos.views_proyectos import (
    proyectos_create,
    proyectos_edit,
    proyectos_list,
)
from catalogos.views_clientes import (
    cliente_create,
    cliente_edit,
    cliente_quick_create,
    clientes_list,
)
from catalogos.views_almacenes import (
    almacenes_confirm_delete,
    almacenes_create,
    almacenes_edit,
    almacenes_list,
)
from catalogos.views_importaciones import (
    importar_clientes,
    importar_productos,
    importar_proveedores,
)

__all__ = [
    "categorias_create",
    "categorias_edit",
    "categorias_list",
    "parametros_sistema_create",
    "parametros_sistema_edit",
    "parametros_sistema_list",
    "precio_cliente_edit",
    "precios_clientes_list",
    "precios_productos_list",
    "producto_precio_bitacora",
    "productos_create",
    "productos_delete",
    "productos_edit",
    "productos_list",
    "proveedores_create",
    "proveedores_edit",
    "proveedores_list",
    "proyectos_create",
    "proyectos_edit",
    "proyectos_list",
    "cliente_create",
    "cliente_edit",
    "cliente_quick_create",
    "clientes_list",
    "almacenes_confirm_delete",
    "almacenes_create",
    "almacenes_edit",
    "almacenes_list",
    "importar_clientes",
    "importar_productos",
    "importar_proveedores",
]
