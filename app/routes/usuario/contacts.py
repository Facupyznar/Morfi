"""Feature "Encontrá amigos desde tu agenda".

Flujo desacoplado de la fuente:
    fuente (Google People API / pegado / CSV) -> lista de emails
        -> encontrar_usuarios_por_contactos(...)  (servicio de matching)
        -> sugerencias (cards) -> reutiliza usuario.connect_friend (Friends, PENDIENTE)

NO se persiste la agenda: los emails se cruzan en memoria y solo se guardan en
sesión los IDs de las coincidencias para poder mostrarlas.
"""
import re

from flask import (
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import current_user, login_required

from app.database import db
from app.helpers.contact_matching import (
    encontrar_usuarios_por_contactos,
    normalizar_emails,
)
from app.helpers.friend_suggestions import sugerir_usuarios_por_afinidad
from app.helpers.google_contacts import (
    SCOPE_CONTACTS,
    SCOPE_OTHER_CONTACTS,
    obtener_contactos_google,
)
from app.helpers.oauth import oauth
from app.helpers.security import csrf
from app.models.user import User
from app.routes.usuario import usuario_bp

_SESSION_MATCH_IDS = "contact_match_ids"
_SESSION_MATCH_SOURCE = "contact_match_source"
_EMAIL_FIND_RE = re.compile(r"[^@\s,;<>\"']+@[^@\s,;<>\"']+\.[^@\s,;<>\"']+")

_LOGIN_SCOPES = ("openid", "email", "profile")


# ── Helpers de presentación ───────────────────────────────────────

def _display_name(user_record):
    return getattr(user_record, "name", None) or getattr(user_record, "username", "Usuario")


def _initials(user_record):
    nombre = _display_name(user_record).strip()
    partes = [p for p in nombre.split() if p]
    if len(partes) >= 2:
        return f"{partes[0][0]}{partes[1][0]}".upper()
    return nombre[:2].upper() or "US"


def _incluir_otros_contactos():
    return bool(current_app.config.get("GOOGLE_CONTACTS_INCLUDE_OTHER"))


def _guardar_coincidencias(usuarios, fuente):
    session[_SESSION_MATCH_IDS] = [str(u.user_id) for u in usuarios]
    session[_SESSION_MATCH_SOURCE] = fuente


def _cargar_sugerencias():
    """Reconstruye las cards desde los IDs guardados en sesión.

    Re-valida descubribilidad / actividad por si algo cambió desde el match.
    """
    ids = session.get(_SESSION_MATCH_IDS) or []
    if not ids:
        return []
    usuarios = (
        db.session.query(User)
        .filter(
            User.user_id.in_(ids),
            User.is_active.is_(True),
            User.discoverable_by_contacts.is_(True),
        )
        .all()
    )
    return [
        {
            "id": str(u.user_id),
            "name": _display_name(u),
            "username": u.username,
            "initials": _initials(u),
            "photo_url": getattr(u, "foto_perfil", None),
            "avatar_url": getattr(u, "avatar_url", None),
        }
        for u in usuarios
    ]


# ── Pantalla unificada "Conectar con amigos" ──────────────────────

@usuario_bp.route("/amigos/descubrir")
@usuario_bp.route("/amigos/buscar")  # alias retrocompatible
@login_required
def discover_friends():
    """Orquesta dos secciones que NO se solapan.

    1) "De tu agenda": coincidencias de Google Contacts (servicio de matching).
    2) "Personas con tus mismos gustos": sugerencias por afinidad (servicio
       de recomendación), excluyendo a quienes ya salieron en la sección 1.
    """
    # Sección 1 — De tu agenda (emails en memoria; solo IDs guardados en sesión).
    seccion_agenda = _cargar_sugerencias()
    ids_agenda = [s["id"] for s in seccion_agenda]

    # Sección 2 — Afinidad (siempre se muestra, no depende de Google).
    seccion_afinidad = sugerir_usuarios_por_afinidad(
        current_user, excluir_ids=ids_agenda
    )

    return render_template(
        "usuario/discover_friends.html",
        contact_matches=seccion_agenda,
        affinity_suggestions=seccion_afinidad,
        match_source=session.get(_SESSION_MATCH_SOURCE),
    )


# ── Google Contacts (autorización incremental, separada del login) ─

@usuario_bp.route("/amigos/contactos/conectar")
@csrf.exempt
@login_required
def contacts_connect():
    google = oauth.create_client("google")
    if google is None:
        flash("La conexión con Google no está disponible en este momento.", "warning")
        return redirect(url_for("usuario.discover_friends"))

    scopes = list(_LOGIN_SCOPES) + [SCOPE_CONTACTS]
    if _incluir_otros_contactos():
        scopes.append(SCOPE_OTHER_CONTACTS)

    redirect_uri = current_app.config.get("GOOGLE_CONTACTS_REDIRECT_URI") or url_for(
        "usuario.contacts_callback", _external=True
    )
    # include_granted_scopes=true → autorización incremental: no perdemos el
    # consentimiento ya dado en el login (openid/email/profile).
    return google.authorize_redirect(
        redirect_uri,
        scope=" ".join(scopes),
        include_granted_scopes="true",
    )


@usuario_bp.route("/amigos/contactos/callback")
@csrf.exempt
@login_required
def contacts_callback():
    google = oauth.create_client("google")
    if google is None:
        flash("La conexión con Google no está disponible en este momento.", "warning")
        return redirect(url_for("usuario.discover_friends"))

    try:
        token = google.authorize_access_token()
    except Exception:
        flash("No pudimos validar el acceso a tus contactos de Google.", "danger")
        return redirect(url_for("usuario.discover_friends"))

    try:
        emails, telefonos = obtener_contactos_google(
            token, incluir_otros=_incluir_otros_contactos()
        )
    except Exception:
        flash("No pudimos leer tu agenda de Google. Probá de nuevo.", "danger")
        return redirect(url_for("usuario.discover_friends"))

    # Cruce en memoria. La agenda NO se persiste.
    coincidencias = encontrar_usuarios_por_contactos(
        emails, telefonos, excluir_user_id=current_user.user_id
    )
    _guardar_coincidencias(coincidencias, "google")

    if coincidencias:
        flash(
            f"Encontramos {len(coincidencias)} contacto(s) que ya están en Morfi.",
            "success",
        )
    else:
        flash("Ninguno de tus contactos está en Morfi todavía.", "info")
    return redirect(url_for("usuario.discover_friends"))


# ── Fallback: importación manual (mismo backend de matching) ───────

@usuario_bp.route("/amigos/importar", methods=["POST"])
@login_required
def import_contacts():
    texto = request.form.get("emails", "") or ""

    archivo = request.files.get("csv")
    if archivo and archivo.filename:
        try:
            contenido = archivo.read().decode("utf-8", errors="ignore")
            texto = f"{texto}\n{contenido}"
        except Exception:
            flash("No pudimos leer el archivo. Asegurate de que sea un CSV de texto.", "warning")
            return redirect(url_for("usuario.discover_friends"))

    emails = normalizar_emails(_EMAIL_FIND_RE.findall(texto))
    if not emails:
        flash("No encontramos emails válidos en lo que pegaste.", "warning")
        return redirect(url_for("usuario.discover_friends"))

    coincidencias = encontrar_usuarios_por_contactos(
        emails, excluir_user_id=current_user.user_id
    )
    _guardar_coincidencias(coincidencias, "manual")

    if coincidencias:
        flash(
            f"Encontramos {len(coincidencias)} contacto(s) que ya están en Morfi.",
            "success",
        )
    else:
        flash("Ninguno de esos emails está en Morfi todavía.", "info")
    return redirect(url_for("usuario.discover_friends"))


# ── Privacidad: toggle de descubribilidad ──────────────────────────

@usuario_bp.route("/perfil/privacidad/contactos", methods=["POST"])
@login_required
def toggle_discoverable():
    user_record = db.session.get(User, current_user.user_id)
    if user_record is not None:
        user_record.discoverable_by_contacts = request.form.get("discoverable") == "on"
        db.session.commit()
        if user_record.discoverable_by_contacts:
            flash("Ahora otras personas pueden encontrarte por tus datos de contacto.", "success")
        else:
            flash("Listo: ya no aparecés en las sugerencias por contactos.", "info")
    return redirect(url_for("usuario.security"))
