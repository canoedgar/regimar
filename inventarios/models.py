# inventarios/models.py
from django.db import models
from django.utils import timezone
from catalogos.models import Producto, Proveedor, Proyecto, Almacen
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

    cantidad = models.DecimalField("Cantidad", max_digits=12, decimal_places=2)
    costo_unitario = models.DecimalField("Costo unitario", max_digits=12, decimal_places=2)

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
        (TIPO_CONSUMO_INTERNO, "Consumo interno / servicio"),
        (TIPO_MERMA, "Merma / daño / robo"),
        (TIPO_DEVOLUCION_PROVEEDOR, "Devolución a proveedor"),
        (TIPO_AJUSTE_NEGATIVO, "Ajuste (disminuye stock)"),
        (TIPO_TRASLADO_SALIDA, "Salida por traslado"),
        (TIPO_PROYECTO, "Salida por poryecto")
    ]

    folio = models.CharField("Folio", max_length=20, unique=True)
    fecha = models.DateField("Fecha", default=timezone.now)
    tipo = models.CharField("Tipo de salida", max_length=3, choices=TIPO_CHOICES)
    proyecto = models.ForeignKey(Proyecto, on_delete=models.PROTECT, null=True, blank=True, related_name="salidas_inventario",)    

    cliente = models.CharField("Cliente", max_length=200, blank=True)
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
    cantidad = models.DecimalField("Cantidad", max_digits=12, decimal_places=2)
    precio_unitario = models.DecimalField("Precio unitario", max_digits=12, decimal_places=2, default=0)

    class Meta:
        verbose_name = "Detalle de salida"
        verbose_name_plural = "Detalles de salidas"

    def __str__(self):
        return f"{self.producto} x {self.cantidad}"

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
        decimal_places=4,
        default=0
    )

    class Meta:
        unique_together = ("producto", "almacen")
        verbose_name = "Stock por almacén"
        verbose_name_plural = "Stocks por almacén"

    def __str__(self):
        return f"{self.producto} | {self.almacen} = {self.cantidad}"

