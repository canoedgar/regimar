from pathlib import Path
import os
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Cargar .env
load_dotenv(BASE_DIR / ".env")


def env_bool(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def env_int(name, default):
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def env_list(name, default=""):
    value = os.getenv(name, default)
    return [item.strip() for item in value.split(",") if item.strip()]

# =========================
# CONFIG BÁSICA
# =========================

SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-insegura")
DEBUG = os.getenv("DEBUG", "True") == "True"

ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "localhost,127.0.0.1,192.168.68.113,192.168.68.114,192.168.1.19")

# =========================
# APPS INSTALADAS
# =========================

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "widget_tweaks",
    "django.contrib.humanize",     


    # Apps creadas por el desarrollador
    "accounts",
    "cartera",
    "catalogos",
    "cotizaciones",
    "inventarios",
    "ventas",
    "proyectos",
    "notificaciones",
    "costos",
]

# =========================
# MIDDLEWARE
# =========================

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "accounts.middleware.SessionSecurityMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# =========================
# BASE DE DATOS (MySql)
# =========================

DATABASES = {
    "default": {
        "ENGINE": os.getenv("DB_ENGINE", "django.db.backends.mysql"),
        "NAME": os.getenv("DB_NAME"),
        "USER": os.getenv("DB_USER"),
        "PASSWORD": os.getenv("DB_PASSWORD"),
        "HOST": os.getenv("DB_HOST"),
        "PORT": os.getenv("DB_PORT", "3306"),
    }
}

# =========================
# PASSWORDS
# =========================

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 8},
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

# =========================
# INTERNACIONALIZACIÓN
# =========================

LANGUAGE_CODE = "es-mx"
TIME_ZONE = "America/Hermosillo"
USE_I18N = True
USE_TZ = True

# =========================
# STATIC & MEDIA
# =========================

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# =========================
# CORREO / NOTIFICACIONES
# =========================

# En desarrollo se usa consola por seguridad; en producción configura SMTP desde .env.
EMAIL_BACKEND = os.getenv(
    "EMAIL_BACKEND",
    "django.core.mail.backends.console.EmailBackend" if DEBUG else "django.core.mail.backends.smtp.EmailBackend",
)
EMAIL_HOST = os.getenv("EMAIL_HOST", "")
EMAIL_PORT = env_int("EMAIL_PORT", 587)
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
EMAIL_USE_SSL = env_bool("EMAIL_USE_SSL", False)
EMAIL_TIMEOUT = env_int("EMAIL_TIMEOUT", 20)
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", EMAIL_HOST_USER or "notificaciones@cpcalimentos.com")
SERVER_EMAIL = os.getenv("SERVER_EMAIL", DEFAULT_FROM_EMAIL)
NOTIFICACIONES_REPORTES_DESTINATARIOS = env_list("NOTIFICACIONES_REPORTES_DESTINATARIOS", "")

# =========================
# SEGURIDAD DE SESIÓN / PRODUCCIÓN
# =========================

# Dominio(s) confiables para formularios POST cuando el sistema esté publicado con HTTPS.
# Ejemplo .env:
# CSRF_TRUSTED_ORIGINS=https://portal.cpcalimentos.com,https://cpcalimentos.com
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS", "")

# Cuando Django está detrás de Nginx/Proxy con HTTPS, esta cabecera permite detectar
# correctamente que la petición original fue segura. Nginx debe enviar:
# proxy_set_header X-Forwarded-Proto $scheme;
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# En producción deben quedar activos. En desarrollo local se pueden desactivar desde .env.
SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", not DEBUG)
SESSION_COOKIE_SECURE = env_bool("SESSION_COOKIE_SECURE", not DEBUG)
CSRF_COOKIE_SECURE = env_bool("CSRF_COOKIE_SECURE", not DEBUG)

# Mitigación contra robo de cookies/sesión desde scripts o contextos externos.
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = os.getenv("SESSION_COOKIE_SAMESITE", "Lax")
SESSION_COOKIE_NAME = os.getenv("SESSION_COOKIE_NAME", "cpc_sessionid")
CSRF_COOKIE_SAMESITE = os.getenv("CSRF_COOKIE_SAMESITE", "Lax")
CSRF_COOKIE_NAME = os.getenv("CSRF_COOKIE_NAME", "cpc_csrftoken")

# Caducidad de sesión.
# SESSION_IDLE_TIMEOUT controla inactividad real; cada request válida renueva la actividad.
# SESSION_ABSOLUTE_TIMEOUT limita el tiempo máximo aunque el usuario siga activo.
SESSION_IDLE_TIMEOUT = env_int("SESSION_IDLE_TIMEOUT", 60 * 30)          # 30 minutos
SESSION_ABSOLUTE_TIMEOUT = env_int("SESSION_ABSOLUTE_TIMEOUT", 60 * 60 * 8)  # 8 horas
SESSION_COOKIE_AGE = env_int("SESSION_COOKIE_AGE", SESSION_ABSOLUTE_TIMEOUT)
SESSION_SAVE_EVERY_REQUEST = env_bool("SESSION_SAVE_EVERY_REQUEST", True)
SESSION_EXPIRE_AT_BROWSER_CLOSE = env_bool("SESSION_EXPIRE_AT_BROWSER_CLOSE", True)

# Validación antifraude básica de sesión.
# El User-Agent ayuda a invalidar cookies robadas y reutilizadas desde otro navegador.
# IP se deja apagado por default porque en redes móviles/proxy puede cambiar y cerrar sesiones válidas.
SESSION_BIND_USER_AGENT = env_bool("SESSION_BIND_USER_AGENT", True)
SESSION_BIND_IP = env_bool("SESSION_BIND_IP", False)

# Headers de seguridad HTTP recomendados para publicación en nube.
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SECURE_REFERRER_POLICY = "same-origin"

# HSTS solo debe activarse cuando HTTPS y el dominio estén funcionando correctamente.
SECURE_HSTS_SECONDS = env_int("SECURE_HSTS_SECONDS", 0 if DEBUG else 31536000)
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", not DEBUG)
SECURE_HSTS_PRELOAD = env_bool("SECURE_HSTS_PRELOAD", False)

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "home"
LOGOUT_REDIRECT_URL = "login"

