"""Lectura de contactos desde Google People API.

Esta es UNA fuente posible de contactos. Su única responsabilidad es, dado un
token OAuth con el scope adecuado, devolver listas de emails y teléfonos. No
hace matching ni toca el módulo social: eso queda para el servicio de matching
desacoplado (``helpers/contact_matching.py``).

NO se persiste la agenda: las listas se devuelven en memoria para el cruce y
luego se descartan.
"""
from app.helpers.oauth import oauth

# Scopes incrementales (se piden al tocar "Encontrá amigos", no en el login).
SCOPE_CONTACTS = "https://www.googleapis.com/auth/contacts.readonly"
SCOPE_OTHER_CONTACTS = "https://www.googleapis.com/auth/contacts.other.readonly"

_CONNECTIONS_URL = "https://people.googleapis.com/v1/people/me/connections"
_OTHER_CONTACTS_URL = "https://people.googleapis.com/v1/otherContacts"
_PAGE_SIZE = 1000
_PERSON_FIELDS = "names,emailAddresses,phoneNumbers"


def _extraer(persona, emails, telefonos):
    for entrada in persona.get("emailAddresses", []) or []:
        valor = (entrada.get("value") or "").strip()
        if valor:
            emails.add(valor.lower())
    for entrada in persona.get("phoneNumbers", []) or []:
        valor = (entrada.get("value") or "").strip()
        if valor:
            telefonos.add(valor)


def _paginar(google, url, token, items_key, params_base):
    emails, telefonos = set(), set()
    page_token = None
    while True:
        params = dict(params_base)
        if page_token:
            params["pageToken"] = page_token
        respuesta = google.get(url, params=params, token=token)
        respuesta.raise_for_status()
        data = respuesta.json()
        for persona in data.get(items_key, []) or []:
            _extraer(persona, emails, telefonos)
        page_token = data.get("nextPageToken")
        if not page_token:
            break
    return emails, telefonos


def obtener_contactos_google(token, incluir_otros=False):
    """Devuelve ``(emails, telefonos)`` (listas) leídos de la agenda de Google.

    - ``connections.list`` → contactos guardados (usa ``personFields``).
    - ``otherContacts.list`` → "otros contactos" (usa ``readMask``), opcional.
    Pagina con ``pageToken`` hasta traer todo.
    """
    google = oauth.create_client("google")
    if google is None:
        return [], []

    emails, telefonos = _paginar(
        google,
        _CONNECTIONS_URL,
        token,
        "connections",
        {"personFields": _PERSON_FIELDS, "pageSize": _PAGE_SIZE},
    )

    if incluir_otros:
        otros_emails, otros_tels = _paginar(
            google,
            _OTHER_CONTACTS_URL,
            token,
            "otherContacts",
            {"readMask": _PERSON_FIELDS, "pageSize": _PAGE_SIZE},
        )
        emails |= otros_emails
        telefonos |= otros_tels

    return list(emails), list(telefonos)
