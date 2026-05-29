from django.db import migrations


def crear_parametro_vigencia(apps, schema_editor):
    ParametroSistema = apps.get_model("catalogos", "ParametroSistema")
    ParametroSistema.objects.get_or_create(
        clave="PRECIO_VIGENCIA_COTIZACIONES",
        defaults={
            "nombre": "Vigencia de cotizaciones",
            "valor": "30",
            "descripcion": "Días sugeridos para calcular fecha_actual + vigencia en el módulo de cotizaciones.",
            "activo": True,
        },
    )


class Migration(migrations.Migration):

    dependencies = [
        ("cotizaciones", "0002_cotizacionpreciodetalle_cantidad_cajas_and_more"),
        ("catalogos", "0020_alter_cliente_options_and_more"),
    ]

    operations = [
        migrations.RunPython(crear_parametro_vigencia, migrations.RunPython.noop),
    ]
