"""Cliente OAuth (Authlib) para el login social con Google.

El proveedor se registra con el documento de descubrimiento OpenID Connect, de
modo que Authlib resuelve automáticamente los endpoints y valida el id_token.
Las credenciales se leen de la configuración (variables de entorno); si no
están definidas, el proveedor no se registra y el botón de Google queda
deshabilitado de forma segura (sin romper el resto de la app).
"""
from authlib.integrations.flask_client import OAuth

GOOGLE_DISCOVERY_URL = "https://accounts.google.com/.well-known/openid-configuration"

oauth = OAuth()


def init_oauth(app):
    oauth.init_app(app)

    client_id = app.config.get("GOOGLE_CLIENT_ID")
    client_secret = app.config.get("GOOGLE_CLIENT_SECRET")
    if not client_id or not client_secret:
        # Sin credenciales no registramos el proveedor: oauth.create_client("google")
        # devolverá None y las rutas avisan que el login con Google no está disponible.
        return

    oauth.register(
        name="google",
        client_id=client_id,
        client_secret=client_secret,
        server_metadata_url=GOOGLE_DISCOVERY_URL,
        client_kwargs={"scope": "openid email profile"},
    )
