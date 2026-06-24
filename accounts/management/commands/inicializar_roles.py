from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand


ROLES_PERMISOS = {
    "Administrador": [
        "catalogos.view_categoria", "catalogos.add_categoria", "catalogos.change_categoria", "catalogos.delete_categoria",
        "catalogos.view_producto", "catalogos.add_producto", "catalogos.change_producto", "catalogos.delete_producto",
        "catalogos.view_proveedor", "catalogos.add_proveedor", "catalogos.change_proveedor", "catalogos.delete_proveedor",
        "catalogos.view_proyecto", "catalogos.add_proyecto", "catalogos.change_proyecto", "catalogos.delete_proyecto",
        "catalogos.view_cliente", "catalogos.add_cliente", "catalogos.change_cliente", "catalogos.delete_cliente",
        "catalogos.view_almacen", "catalogos.add_almacen", "catalogos.change_almacen", "catalogos.delete_almacen",
        "catalogos.view_parametrosistema", "catalogos.add_parametrosistema", "catalogos.change_parametrosistema", "catalogos.delete_parametrosistema",
        "catalogos.view_clienteproductoprecio", "catalogos.add_clienteproductoprecio", "catalogos.change_clienteproductoprecio", "catalogos.delete_clienteproductoprecio",
        "catalogos.view_preciomenorminimoautorizacion", "catalogos.add_preciomenorminimoautorizacion", "catalogos.change_preciomenorminimoautorizacion", "catalogos.delete_preciomenorminimoautorizacion",
        "inventarios.view_entradainventario", "inventarios.add_entradainventario", "inventarios.change_entradainventario", "inventarios.delete_entradainventario",
        "inventarios.view_salidainventario", "inventarios.add_salidainventario", "inventarios.change_salidainventario", "inventarios.delete_salidainventario",
        "ventas.view_notaventa", "ventas.add_notaventa", "ventas.change_notaventa", "ventas.delete_notaventa",
        "inventarios.view_inventariostock", "inventarios.add_inventariostock", "inventarios.change_inventariostock", "inventarios.delete_inventariostock",
        "cartera.view_pagocliente", "cartera.add_pagocliente", "cartera.change_pagocliente", "cartera.delete_pagocliente",
        "cartera.view_pagoaplicacionnota", "cartera.add_pagoaplicacionnota", "cartera.change_pagoaplicacionnota", "cartera.delete_pagoaplicacionnota",
        "cartera.view_clientesaldofavormovimiento", "cartera.add_clientesaldofavormovimiento", "cartera.change_clientesaldofavormovimiento", "cartera.delete_clientesaldofavormovimiento",
        "cotizaciones.view_cotizacionprecio", "cotizaciones.add_cotizacionprecio", "cotizaciones.change_cotizacionprecio", "cotizaciones.delete_cotizacionprecio",
    ],
    "Catalogos": [
        "catalogos.view_categoria", "catalogos.add_categoria", "catalogos.change_categoria", "catalogos.delete_categoria",
        "catalogos.view_producto", "catalogos.add_producto", "catalogos.change_producto", "catalogos.delete_producto",
        "catalogos.view_proveedor", "catalogos.add_proveedor", "catalogos.change_proveedor", "catalogos.delete_proveedor",
        "catalogos.view_proyecto", "catalogos.add_proyecto", "catalogos.change_proyecto", "catalogos.delete_proyecto",
        "catalogos.view_cliente", "catalogos.add_cliente", "catalogos.change_cliente", "catalogos.delete_cliente",
        "catalogos.view_almacen", "catalogos.add_almacen", "catalogos.change_almacen", "catalogos.delete_almacen",
    ],
    "Inventarios": [
        "catalogos.view_producto", "catalogos.view_proveedor", "catalogos.add_proveedor", "catalogos.view_almacen",
        "inventarios.view_entradainventario", "inventarios.add_entradainventario", "inventarios.change_entradainventario",
        "inventarios.view_salidainventario", "inventarios.add_salidainventario", "inventarios.change_salidainventario",
        "inventarios.view_inventariostock", "inventarios.change_inventariostock",
    ],
    "Ventas": [
        "catalogos.view_cliente", "catalogos.add_cliente",
        "catalogos.view_producto", "catalogos.view_almacen", "catalogos.view_clienteproductoprecio",
        "ventas.view_notaventa", "ventas.add_notaventa", "ventas.change_notaventa",
        "cotizaciones.view_cotizacionprecio", "cotizaciones.add_cotizacionprecio", "cotizaciones.change_cotizacionprecio",
        "cartera.view_pagocliente", "cartera.add_pagocliente",
    ],
    "Cartera": [
        "catalogos.view_cliente",
        "ventas.view_notaventa",
        "cartera.view_pagocliente", "cartera.add_pagocliente", "cartera.change_pagocliente",
        "cartera.view_pagoaplicacionnota", "cartera.add_pagoaplicacionnota", "cartera.change_pagoaplicacionnota",
        "cartera.view_clientesaldofavormovimiento", "cartera.add_clientesaldofavormovimiento", "cartera.change_clientesaldofavormovimiento",
    ],
}

class Command(BaseCommand):
    help = "Crea/actualiza los roles base del sistema y les asigna permisos CRUD iniciales."

    def add_arguments(self, parser):
        parser.add_argument(
            "--merge",
            action="store_true",
            help="Agrega permisos sin quitar permisos existentes. Por defecto sincroniza exactamente la matriz base.",
        )

    def handle(self, *args, **options):
        merge = options["merge"]
        total_roles = 0
        faltantes_globales = []

        for role_name, perm_codes in ROLES_PERMISOS.items():
            group, _ = Group.objects.get_or_create(name=role_name)
            permisos = []
            faltantes = []

            for code in perm_codes:
                app_label, codename = code.split(".", 1)
                permiso = Permission.objects.filter(content_type__app_label=app_label, codename=codename).first()
                if permiso:
                    permisos.append(permiso)
                else:
                    faltantes.append(code)

            if merge:
                group.permissions.add(*permisos)
            else:
                group.permissions.set(permisos)

            total_roles += 1
            if faltantes:
                faltantes_globales.extend(f"{role_name}: {code}" for code in faltantes)

            self.stdout.write(self.style.SUCCESS(f"Rol sincronizado: {role_name} ({len(permisos)} permisos)."))

        if faltantes_globales:
            self.stdout.write(self.style.WARNING("Permisos no encontrados:"))
            for item in faltantes_globales:
                self.stdout.write(f" - {item}")

        self.stdout.write(self.style.SUCCESS(f"Proceso terminado. Roles procesados: {total_roles}."))
