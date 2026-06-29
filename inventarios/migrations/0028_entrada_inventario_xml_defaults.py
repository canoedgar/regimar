# Generated manually to align EntradaInventario XML fields with existing databases.

from django.db import migrations, models


def _column_exists(connection, table_name, column_name):
    with connection.cursor() as cursor:
        existing_columns = {
            column.name
            for column in connection.introspection.get_table_description(cursor, table_name)
        }
    return column_name in existing_columns


def _add_field_if_missing(apps, schema_editor, *, name, field):
    EntradaInventario = apps.get_model("inventarios", "EntradaInventario")
    table_name = EntradaInventario._meta.db_table
    if _column_exists(schema_editor.connection, table_name, name):
        return

    field.set_attributes_from_name(name)
    schema_editor.add_field(EntradaInventario, field)


def ensure_xml_columns(apps, schema_editor):
    _add_field_if_missing(
        apps,
        schema_editor,
        name="tiene_xml",
        field=models.BooleanField(
            default=False,
            verbose_name="Tiene XML",
            help_text="Indica si la entrada cuenta con XML de factura asociado.",
        ),
    )
    _add_field_if_missing(
        apps,
        schema_editor,
        name="xml_contenido",
        field=models.TextField(
            blank=True,
            default="",
            verbose_name="Contenido XML",
            help_text="Contenido XML de factura asociado a la entrada, cuando aplique.",
        ),
    )


def noop_reverse(apps, schema_editor):
    # No se eliminan columnas para evitar pérdida accidental de XML histórico.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("inventarios", "0027_comision_terminal_venta"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(ensure_xml_columns, noop_reverse),
            ],
            state_operations=[
                migrations.AddField(
                    model_name="entradainventario",
                    name="tiene_xml",
                    field=models.BooleanField(
                        default=False,
                        help_text="Indica si la entrada cuenta con XML de factura asociado.",
                        verbose_name="Tiene XML",
                    ),
                ),
                migrations.AddField(
                    model_name="entradainventario",
                    name="xml_contenido",
                    field=models.TextField(
                        blank=True,
                        default="",
                        help_text="Contenido XML de factura asociado a la entrada, cuando aplique.",
                        verbose_name="Contenido XML",
                    ),
                ),
            ],
        ),
    ]
