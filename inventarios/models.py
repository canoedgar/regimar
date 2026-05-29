# inventarios/models.py
from django.db import models
from django.conf import settings
from django.utils import timezone
from catalogos.models import Producto, Proveedor, Proyecto, Almacen, Cliente
from django.core.exceptions import ValidationError


class EntradaInventario(models.Model):
    # Entradas existentes (se conservan)
    TIPO_OC_CON_FACTURA = "OCF"        
    TIPO_ENTRADA_MANUAL = "MAN"  
    TIPO_AJUSTE_POSITIVO = "AJP"     
    TIPO_TRASLADO = "TRE" 
    TIPO_RETORNO = "RTN"

    TIPO_CHOICES = [
        (TIPO_OC_CON_FACTURA, "Factura"),        
        (TIPO_ENTRADA_MANUAL, "Entrada nota / remisión"),        
        (TIPO_AJUSTE_POSITIVO, "Ajuste (aumenta stock)"),        
        (TIPO_TRASLADO, "Entrada por traspaso"),        
        (TIPO_RETORNO, "Retorno")
    ]

    folio = models.CharField("Folio", max_length=20, unique=True)
    fecha = models.DateField("Fecha", default=timezone.now)
    tipo = models.CharField("Tipo de entrada", max_length=3, choices=TIPO_CHOICES)

    # proveedor = models.CharField("Proveedor", max_length=200, blank=True)

    proveedor = models.ForeignKey(
        Proveedor,
        on_delete=models.PROTECT,
        null=True,        
        blank=True,
    )

    proyecto = models.ForeignKey(
        Proyecto,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="retornos_inventario",
    )

    # Documento soporte (nota/remisión/devolución, etc.)
    documento_referencia = models.CharField(
        "Documento referencia",
        max_length=60,
        blank=True,
        help_text="Ej: Nota, remisión, devolución, etc.",
    )



    almacen = models.ForeignKey(
        "catalogos.Almacen",
        on_delete=models.PROTECT,
        related_name="entradas_inventario",      
        null=True,
        blank=True,
    )



    # Datos de factura (si aplica)
    uuid_factura = models.CharField(
        "UUID factura",
        max_length=40,
        blank=True,
        null=True,   
        unique=True
    )

    tiene_xml = models.BooleanField("Tiene XML", default=False)
    xml_contenido = models.TextField("Contenido XML", blank=True)
    motivo = models.TextField("Motivo", blank=True)
    observaciones = models.TextField("Observaciones", blank=True)    
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Entrada de inventario"
        verbose_name_plural = "Entradas de inventario"
        ordering = ["-fecha", "-folio"]

    def __str__(self):
        return f"{self.folio} - {self.get_tipo_display()}"

    def clean(self):
        super().clean()

        if self.tipo == self.TIPO_RETORNO and not self.proyecto_id:
            raise ValidationError({"proyecto": "Selecciona un proyecto para el retorno."})

        if self.tipo != self.TIPO_RETORNO and self.proyecto_id:
            raise ValidationError({"proyecto": "Este campo solo aplica para retorno de proyecto."})
        
        tipos_requieren_proveedor = [
            self.TIPO_OC_CON_FACTURA,
            self.TIPO_ENTRADA_MANUAL            
        ]

        if self.tipo in tipos_requieren_proveedor and not self.proveedor_id:
            raise ValidationError({"proveedor": "Selecciona un proveedor."})


class EntradaInventarioDetalle(models.Model):
    entrada = models.ForeignKey(
        EntradaInventario,
        on_delete=models.CASCADE,
        related_name="detalles",
    )
    producto = models.ForeignKey(Producto, on_delete=models.PROTECT)

    almacen = models.ForeignKey(  
        "catalogos.Almacen",
        on_delete=models.PROTECT,
        related_name="entradas_detalle",
        null=True,
        blank=True,
    )

    presentacion_nombre = models.CharField(
        "Presentación",
        max_length=120,
        blank=True,
        help_text="Ej: Kilos, Caja 20 kg, Caja 10 kg.",
    )
    presentacion_conversion_id = models.CharField(
        "ID de conversión usada",
        max_length=50,
        blank=True,
        help_text="Identificador de la presentación/conversión usada al capturar la entrada.",
    )
    cantidad_presentacion = models.DecimalField(
        "Cantidad capturada en presentación",
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Cantidad original capturada por el usuario. Ej: 2 cajas.",
    )
    presentacion_factor_conversion = models.DecimalField(
        "Factor de conversión a métrica base",
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Cantidad de métrica base que entra por cada unidad de presentación. Ej: 20 kg por caja.",
    )
    presentacion_metrica_default = models.CharField(
        "Métrica base",
        max_length=50,
        blank=True,
        help_text="Métrica en la que se incrementa inventario. Ej: kg.",
    )
    presentacion_equivalencia_texto = models.CharField(
        "Equivalencia usada",
        max_length=160,
        blank=True,
        help_text="Texto histórico de la equivalencia aplicada. Ej: 1 Caja 20 kg = 20 kg.",
    )
    cantidad = models.DecimalField(
        "Cantidad agregada al inventario",
        max_digits=14,
        decimal_places=2,
        help_text="Cantidad ya convertida a la métrica base del inventario.",
    )
    costo_unitario = models.DecimalField("Costo unitario", max_digits=12, decimal_places=2)
    es_peso_variable = models.BooleanField(
        "Entrada con peso variable",
        default=False,
        help_text="Indica que la cantidad de inventario se capturó con kilos reales y cajas informativas.",
    )
    cantidad_cajas = models.DecimalField(
        "Cantidad de cajas",
        max_digits=14,
        decimal_places=2,
        default=0,
        help_text="Número de cajas recibidas para productos con peso variable.",
    )
    kilos_reales = models.DecimalField(
        "Kilos reales",
        max_digits=14,
        decimal_places=2,
        default=0,
        help_text="Kilos reales recibidos para productos con peso variable.",
    )
    costo_total = models.DecimalField(
        "Costo total",
        max_digits=14,
        decimal_places=2,
        default=0,
        help_text="Costo total de la línea al momento de capturar la entrada.",
    )

    class Meta:
        verbose_name = "Detalle de entrada"
        verbose_name_plural = "Detalles de entradas"

    def __str__(self):
        return f"{self.producto} x {self.cantidad}"


class SalidaInventario(models.Model):    
    TIPO_VENTA = "VTA"
    TIPO_CONSUMO_INTERNO = "CON"
    TIPO_MERMA = "MRM"
    TIPO_DEVOLUCION_PROVEEDOR = "DEV"
    TIPO_AJUSTE_NEGATIVO = "AJN"   
    TIPO_TRASLADO_SALIDA = "TRS"   
    TIPO_PROYECTO = "PRY"

    TIPO_CHOICES = [
        (TIPO_VENTA, "Salida por venta"),        
        (TIPO_AJUSTE_NEGATIVO, "Ajuste (disminuye stock)")        
    ]

    folio = models.CharField("Folio", max_length=20, unique=True)
    fecha = models.DateField("Fecha", default=timezone.now)
    tipo = models.CharField("Tipo de salida", max_length=3, choices=TIPO_CHOICES)
    proyecto = models.ForeignKey(Proyecto, on_delete=models.PROTECT, null=True, blank=True, related_name="salidas_inventario",)    

    cliente = models.CharField("Cliente", max_length=200, blank=True)
    cliente_ref = models.ForeignKey(
        Cliente,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ventas_inventario",
        help_text="Cliente del catálogo usado para historial de precios.",
    )
    FORMA_PAGO_CONTADO = "CONTADO"
    FORMA_PAGO_CREDITO = "CREDITO"
    FORMA_PAGO_CHOICES = [
        (FORMA_PAGO_CONTADO, "Contado"),
        (FORMA_PAGO_CREDITO, "Crédito"),
    ]
    forma_pago_venta = models.CharField(
        "Forma de pago de venta",
        max_length=10,
        choices=FORMA_PAGO_CHOICES,
        default=FORMA_PAGO_CONTADO,
    )

    ESTADO_PAGO_PAGADO = "PAG"
    ESTADO_PAGO_PENDIENTE = "PEND"
    ESTADO_PAGO_CHOICES = [
        (ESTADO_PAGO_PAGADO, "Pagado"),
        (ESTADO_PAGO_PENDIENTE, "Pendiente de pago"),
    ]
    estado_pago = models.CharField(
        "Estado de pago",
        max_length=4,
        choices=ESTADO_PAGO_CHOICES,
        default=ESTADO_PAGO_PENDIENTE,
        db_index=True,
        help_text="Estado administrativo de pago de la nota; no depende de la forma de pago.",
    )

    cliente_direccion = models.TextField("Dirección del cliente para esta venta", blank=True)
    cliente_contacto = models.CharField("Contacto del cliente para esta venta", max_length=200, blank=True)
    proveedor = models.CharField("Proveedor", max_length=200, blank=True) 

    almacen = models.ForeignKey(
        "catalogos.Almacen",
        on_delete=models.PROTECT,
        related_name="salidas_inventario",  # o salidas_inventario
        null=True,
        blank=True,
    )


    documento_referencia = models.CharField("Documento referencia", max_length=60, blank=True)
    motivo = models.TextField("Motivo", blank=True)
    observaciones = models.TextField("Observaciones", blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    ESTADO_ACTIVA = "ACT"
    ESTADO_CANCELADA = "CAN"
    ESTADO_CHOICES = [
        (ESTADO_ACTIVA, "Activa"),
        (ESTADO_CANCELADA, "Cancelada"),
    ]

    estado = models.CharField(
        "Estado",
        max_length=3,
        choices=ESTADO_CHOICES,
        default=ESTADO_ACTIVA,
        db_index=True,
    )
    cancelada_en = models.DateTimeField("Cancelada en", null=True, blank=True)
    motivo_cancelacion = models.TextField("Motivo de cancelación", blank=True)

    editada_en = models.DateTimeField("Editada en", null=True, blank=True)
    editada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notas_venta_editadas",
    )

    class Meta:
        verbose_name = "Salida de inventario"
        verbose_name_plural = "Salidas de inventario"
        ordering = ["-fecha", "-folio"]

    def __str__(self):
        return f"{self.folio} - {self.get_tipo_display()}"

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.tipo == self.TIPO_PROYECTO and not self.proyecto:
            raise ValidationError({"proyecto": "Selecciona un proyecto para este tipo de salida."})
        if self.tipo != self.TIPO_PROYECTO and self.proyecto_id:            
            raise ValidationError({"proyecto": "Este campo solo aplica para salidas por proyecto."})



class SalidaInventarioDetalle(models.Model):
    salida = models.ForeignKey(
        SalidaInventario,
        on_delete=models.CASCADE,
        related_name="detalles",
    )
    producto = models.ForeignKey(Producto, on_delete=models.PROTECT)
    almacen = models.ForeignKey(
        "catalogos.Almacen",
        on_delete=models.PROTECT,
        related_name="salidas_detalle",
        null=True,
        blank=True,
        help_text="Almacén principal del renglón. Para ventas surtidas de varios almacenes usar asignaciones.",
    )
    presentacion_nombre = models.CharField(
        "Presentación",
        max_length=120,
        blank=True,
        help_text="Ej: Kilos, Caja 20 kg, Caja 10 kg.",
    )
    presentacion_conversion_id = models.CharField(
        "ID de conversión usada",
        max_length=50,
        blank=True,
        help_text="Identificador de la presentación/conversión usada al capturar la venta.",
    )
    cantidad_presentacion = models.DecimalField(
        "Cantidad vendida en presentación",
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Cantidad original capturada por el usuario. Ej: 2 cajas.",
    )
    presentacion_factor_conversion = models.DecimalField(
        "Factor de conversión a métrica base",
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Cantidad de métrica base que descuenta cada unidad de presentación. Ej: 20 kg por caja.",
    )
    presentacion_metrica_default = models.CharField(
        "Métrica base",
        max_length=50,
        blank=True,
        help_text="Métrica en la que se descuenta inventario. Ej: kg.",
    )
    presentacion_equivalencia_texto = models.CharField(
        "Equivalencia usada",
        max_length=160,
        blank=True,
        help_text="Texto histórico de la equivalencia aplicada. Ej: 1 Caja 20 kg = 20 kg.",
    )
    cantidad = models.DecimalField(
        "Cantidad descontada de inventario",
        max_digits=14,
        decimal_places=2,
        help_text="Cantidad ya convertida a la métrica base del inventario.",
    )
    precio_unitario = models.DecimalField("Precio unitario", max_digits=12, decimal_places=2, default=0)
    costo_unitario_aplicado = models.DecimalField(
        "Costo unitario aplicado",
        max_digits=12,
        decimal_places=2,
        default=0,
        help_text="Costo promedio guardado al momento de vender para conservar margen histórico.",
    )

    class Meta:
        verbose_name = "Detalle de salida"
        verbose_name_plural = "Detalles de salidas"

    def __str__(self):
        return f"{self.producto} x {self.cantidad}"


class SalidaInventarioDetalleAlmacen(models.Model):
    """
    Trazabilidad de surtido por almacén para una línea de venta.
    Permite cancelar notas y regresar inventario exactamente al almacén de origen.
    """
    detalle = models.ForeignKey(
        SalidaInventarioDetalle,
        on_delete=models.CASCADE,
        related_name="asignaciones",
    )
    almacen = models.ForeignKey(
        "catalogos.Almacen",
        on_delete=models.PROTECT,
        related_name="salidas_asignadas",
    )
    cantidad = models.DecimalField("Cantidad", max_digits=14, decimal_places=2)

    class Meta:
        verbose_name = "Asignación de salida por almacén"
        verbose_name_plural = "Asignaciones de salida por almacén"

    def __str__(self):
        return f"{self.detalle.producto} | {self.almacen} x {self.cantidad}"

class InventarioStock(models.Model):
    producto = models.ForeignKey(
        Producto,
        on_delete=models.CASCADE,
        related_name="stocks"
    )
    almacen = models.ForeignKey(
        Almacen,
        on_delete=models.CASCADE,
        related_name="stocks"
    )

    cantidad = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0
    )
    costo_promedio = models.DecimalField(
        "Costo promedio",
        max_digits=14,
        decimal_places=2,
        default=0,
        help_text="Costo promedio ponderado del producto en este almacén.",
    )

    class Meta:
        unique_together = ("producto", "almacen")
        verbose_name = "Stock por almacén"
        verbose_name_plural = "Stocks por almacén"

    def __str__(self):
        return f"{self.producto} | {self.almacen} = {self.cantidad}"