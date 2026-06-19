from django import forms

UNIVERSAL_DATE_FORMAT = "%Y-%m-%d"
UNIVERSAL_DATE_INPUT_FORMATS = [UNIVERSAL_DATE_FORMAT]
UNIVERSAL_DATE_PLACEHOLDER = "YYYY-MM-DD"
UNIVERSAL_DATE_PATTERN = r"\d{4}-\d{2}-\d{2}"


class UniversalDateInput(forms.DateInput):
    """
    Date widget for operational screens.

    Uses a text input so the date remains visually stable as YYYY-MM-DD
    regardless of browser language/locale. Backend parsing remains ISO-only.
    """

    input_type = "text"

    def __init__(self, attrs=None, format=None):
        merged_attrs = {
            "class": "form-control",
            "placeholder": UNIVERSAL_DATE_PLACEHOLDER,
            "pattern": UNIVERSAL_DATE_PATTERN,
            "inputmode": "numeric",
            "autocomplete": "off",
            "title": "Formato requerido: YYYY-MM-DD",
            "data-date-format": "YYYY-MM-DD",
        }
        if attrs:
            merged_attrs.update(attrs)
        merged_attrs.pop("type", None)
        super().__init__(attrs=merged_attrs, format=format or UNIVERSAL_DATE_FORMAT)
