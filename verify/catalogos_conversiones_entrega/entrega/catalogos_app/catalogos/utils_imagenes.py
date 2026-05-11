# catalogos/utils_imagenes.py
import base64
import io
from PIL import Image


def imagen_a_base64_comprimida(
    uploaded_file,
    max_size=(256, 256),
    max_bytes=80 * 1024,  # ~80 KB, puedes ajustar
):
    """
    - Redimensiona la imagen manteniendo proporción, con máximo 256x256
    - La guarda como JPEG comprimido
    - Ajusta calidad hasta que pese <= max_bytes o llegue a un mínimo razonable
    - Regresa la cadena Base64 (str)
    """
    if not uploaded_file:
        return None

    # Abrir imagen desde el archivo subido
    img = Image.open(uploaded_file)

    # Convertir a RGB si viene con alfa u otro modo
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")

    # Redimensionar manteniendo proporción, sin exceder max_size
    img.thumbnail(max_size, Image.LANCZOS)

    # Probar calidades decrecientes hasta llegar al tamaño deseado
    calidad = 85
    buffer = io.BytesIO()

    while calidad >= 40:  # no bajar de calidad 40 para no destruir la imagen
        buffer.seek(0)
        buffer.truncate(0)

        img.save(buffer, format="JPEG", optimize=True, quality=calidad)
        size = buffer.tell()

        if size <= max_bytes:
            break

        calidad -= 5  # bajamos un poco la calidad y volvemos a intentar

    buffer.seek(0)
    # Codificar como base64
    return base64.b64encode(buffer.read()).decode("utf-8")
