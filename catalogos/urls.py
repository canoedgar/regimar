from django.urls import path

import proyectos
from .views import (
    productos_list, productos_create, productos_create_from_xml, productos_edit, productos_delete,
    proveedores_list, proveedores_create, proveedores_edit,
    categorias_list, categorias_create, categorias_edit, 
    proyectos_list, proyectos_create, proyectos_edit,
    clientes_list, cliente_create, cliente_edit,
    almacenes_list, almacenes_create, almacenes_edit, almacenes_confirm_delete,
    importar_clientes, importar_productos, importar_proveedores
)

urlpatterns = [
    # Productos
    path("productos/", productos_list, name="productos_list"),
    path("productos/nuevo/", productos_create, name="productos_form"),
    path("productos/<int:pk>/editar", productos_edit, name="productos_edit"),
    path("productos/<int:pk>/eliminar/", productos_delete, name="productos_delete"),
    path("catalogos/productos/nuevo-desde-xml/", productos_create_from_xml, name="productos_create_from_xml"),

    # Proveedores
    path("proveedores/", proveedores_list, name="proveedores_list"),
    path("proveedores/nuevo/", proveedores_create, name="proveedores_form"),
    path("proveedores/<int:pk>/editar/", proveedores_edit, name="proveedores_edit"),

    # Categorías
    path("categorias/", categorias_list, name="categorias_list"),
    path("categorias/nueva/", categorias_create, name="categorias_form"),
    path("categorias/editar/<int:pk>/", categorias_edit, name="categorias_edit"),

    # Proyectos
    path("proyectos/", proyectos_list, name="proyectos_list"),
    path("proyectos/nuevo/", proyectos_create, name="proyectos_create"),
    path("proyectos/<int:pk>/editar/", proyectos_edit, name="proyectos_edit"),

    #Clientes
    path("clientes/", clientes_list, name="clientes_list"),
    path("clientes/nuevo/", cliente_create, name="cliente_create"),
    path("clientes/<int:pk>/editar/", cliente_edit, name="cliente_edit"),

    #Almacenes
    path("almacenes/", almacenes_list, name="almacenes_list"),
    path("almacenes/nuevo/", almacenes_create, name="almacenes_create"),
    path("almacenes/<int:pk>/editar/", almacenes_edit, name="almacenes_edit"),
    path("almacenes/<int:pk>/eliminar/", almacenes_confirm_delete, name="almacenes_confirm_delete"),

    #Importaciones
    path("importar/productos/", importar_productos, name="importar_productos"),
    path("importar/proveedores/", importar_proveedores, name="importar_proveedores"),
    path("importar/clientes/", importar_clientes, name="importar_clientes"),
]
