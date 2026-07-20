from datetime import datetime, timezone

from flask import jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.database import db
from app.models.notification import Notification
from app.models.notification_prefs import NotificationPrefs
from app.routes.usuario import usuario_bp


def crear_notificacion(user_id, tipo, titulo, descripcion=None, url_destino=None):
    """
    Inserta una notificación in-app para el usuario.
    Llamar desde cualquier evento (reserva, reseña, amistad, etc.)
    """
    try:
        notif = Notification(
            user_id=user_id,
            tipo=tipo,
            titulo=titulo,
            descripcion=descripcion,
            url_destino=url_destino,
        )
        db.session.add(notif)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        import logging
        logging.getLogger(__name__).warning(f"[notif] Error al crear notificación: {e}")


def _time_ago(dt):
    """Devuelve string relativo: 'hace 5 min', 'hace 1 h', 'ayer', etc."""
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    diff = int((now - dt).total_seconds())
    if diff < 60:
        return "ahora"
    if diff < 3600:
        return f"hace {diff // 60} min"
    if diff < 86400:
        return f"hace {diff // 3600} h"
    if diff < 172800:
        return "ayer"
    return dt.strftime("%-d %b").lower()


TIPO_ICON = {
    "review":    ("bi-star",           "#FFF0EB", "#FF6B35"),
    "reserva":   ("bi-calendar-check", "#E8F6F1", "#0B7A56"),
    "respuesta": ("bi-chat-left-text", "#EEF0FF", "#5B5BD6"),
    "amistad":   ("bi-person-plus",    "#F0F0F5", "#6B6B8A"),
    "beneficio": ("bi-gift",           "#FFF0EB", "#FF6B35"),
}


def _serialize(n):
    icon, bg, color = TIPO_ICON.get(n.tipo, ("bi-bell", "#F0F0F5", "#6B6B8A"))
    return {
        "id":          str(n.id_notification),
        "tipo":        n.tipo,
        "titulo":      n.titulo,
        "descripcion": n.descripcion or "",
        "leida":       n.leida,
        "time_ago":    _time_ago(n.fecha),
        "url":         n.url_destino or "#",
        "icon":        icon,
        "icon_bg":     bg,
        "icon_color":  color,
    }


# ── GET /notificaciones/dropdown (JSON para la campanita) ────────────

@usuario_bp.route("/notificaciones/dropdown")
@login_required
def notifications_dropdown():
    items = (
        db.session.query(Notification)
        .filter_by(user_id=current_user.user_id)
        .order_by(Notification.fecha.desc())
        .limit(5)
        .all()
    )
    unread = sum(1 for n in items if not n.leida)
    return jsonify({
        "unread": unread,
        "items":  [_serialize(n) for n in items],
    })


# ── POST /notificaciones/marcar-leidas ───────────────────────────────

@usuario_bp.route("/notificaciones/marcar-leidas", methods=["POST"])
@login_required
def mark_notifications_read():
    db.session.query(Notification).filter_by(
        user_id=current_user.user_id,
        leida=False,
    ).update({"leida": True})
    db.session.commit()
    return jsonify({"ok": True})


# ── POST /notificaciones/<id>/leer (marca una sola) ──────────────────

@usuario_bp.route("/notificaciones/<uuid:id_notification>/leer", methods=["POST"])
@login_required
def mark_notification_read(id_notification):
    notif = db.session.query(Notification).filter_by(
        id_notification=id_notification,
        user_id=current_user.user_id,
    ).first()
    if notif is None:
        return jsonify({"ok": False}), 404

    if not notif.leida:
        notif.leida = True
        db.session.commit()

    unread = db.session.query(Notification).filter_by(
        user_id=current_user.user_id, leida=False
    ).count()
    return jsonify({"ok": True, "unread": unread})


# ── GET /notificaciones (página completa) ────────────────────────────

@usuario_bp.route("/notificaciones")
@login_required
def notifications_page():
    filtro = request.args.get("filtro", "todas")

    query = (
        db.session.query(Notification)
        .filter_by(user_id=current_user.user_id)
        .order_by(Notification.fecha.desc())
    )
    if filtro == "no_leidas":
        query = query.filter_by(leida=False)

    items = [_serialize(n) for n in query.all()]
    unread_count = db.session.query(Notification).filter_by(
        user_id=current_user.user_id, leida=False
    ).count()

    prefs = NotificationPrefs.get_or_create(db.session, current_user.user_id)

    return render_template(
        "usuario/notifications.html",
        items=items,
        filtro=filtro,
        unread_count=unread_count,
        prefs=prefs,
    )


# ── POST /notificaciones/preferencias ────────────────────────────────

@usuario_bp.route("/notificaciones/preferencias", methods=["POST"])
@login_required
def save_notification_prefs():
    prefs = NotificationPrefs.get_or_create(db.session, current_user.user_id)

    def chk(field):
        return request.form.get(field) == "1"

    prefs.review_inapp    = chk("review_inapp")
    prefs.review_mail     = chk("review_mail")
    prefs.respuesta_inapp = chk("respuesta_inapp")
    prefs.respuesta_mail  = chk("respuesta_mail")
    prefs.reserva_inapp   = chk("reserva_inapp")
    prefs.reserva_mail    = chk("reserva_mail")
    prefs.beneficio_inapp = chk("beneficio_inapp")
    prefs.beneficio_mail  = chk("beneficio_mail")
    prefs.amistad_inapp   = chk("amistad_inapp")
    prefs.amistad_mail    = chk("amistad_mail")

    db.session.commit()
    return redirect(url_for("usuario.notifications_page", filtro="preferencias"))