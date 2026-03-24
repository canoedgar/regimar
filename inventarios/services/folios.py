
import re
from ..models import EntradaInventario, SalidaInventario

# Mapea tipo de movimiento -> prefijo folio
FOLIO_PREFIX_BY_TIPO = {

    # Entradas
    getattr(EntradaInventario, "TIPO_OC_CON_FACTURA", "OCF"): "OCF",
    getattr(EntradaInventario, "TIPO_ENTRADA_MANUAL", "MAN"): "MAN",
    getattr(EntradaInventario, "TIPO_AJUSTE_POSITIVO", "AJP"): "AJP",
    getattr(EntradaInventario, "TIPO_TRASLADO", "TRE"): "TRE",
    getattr(EntradaInventario, "TIPO_RETORNO", "RTN"): "RTN",
    

    # Salidas
    getattr(SalidaInventario, "TIPO_VENTA", "VTA"): "VTA",
    getattr(SalidaInventario, "TIPO_PROYECTO", "PRY"): "PRY",
    getattr(SalidaInventario, "TIPO_TRASLADO_SALIDA", "TRS"): "TRS",
    getattr(SalidaInventario, "TIPO_AJUSTE_NEGATIVO", "AJN"): "AJN",
    getattr(SalidaInventario, "TIPO_MERMA", "MRM"): "MRM",
    getattr(SalidaInventario, "TIPO_DEVOLUCION_PROVEEDOR", "DEV"): "DEV",
    getattr(SalidaInventario, "TIPO_CONSUMO_INTERNO", "COI"): "COI",        
    
}

def next_folio_movimiento(*, tipo: str, width: int = 6, prefix: str | None = None) -> str:
    """
    Genera el siguiente folio para un tipo de movimiento.

    - Busca en EntradaInventario y SalidaInventario para evitar choques.

    - Formato: <PREFIX>-000001
    
    - prefix puede forzarse; si no, se toma del mapa FOLIO_PREFIX_BY_TIPO;
      si tampoco existe, usa el tipo.
    """    
    
    pref = (prefix or FOLIO_PREFIX_BY_TIPO.get(tipo) or tipo).strip().upper()    

    # Revisar folios en entradas y salidas para evitar choques
    folios_entradas = EntradaInventario.objects.filter(
        folio__startswith=f"{pref}-"
    ).values_list("folio", flat=True)

    folios_salidas = SalidaInventario.objects.filter(
        folio__startswith=f"{pref}-"
    ).values_list("folio", flat=True)

    max_num = 0
    pat = re.compile(rf"^{re.escape(pref)}-(\d+)$")

    for f in list(folios_entradas) + list(folios_salidas):
        m = pat.match((f or "").strip())
        if m:
            n = int(m.group(1))
            if n > max_num:
                max_num = n

    return f"{pref}-{max_num + 1:0{width}d}"
