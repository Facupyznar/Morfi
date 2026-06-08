from flask_mail import Mail, Message
from flask import current_app

mail = Mail()


def _prefs_allow(user_id, tipo):
    """Devuelve True si el usuario tiene habilitado el mail para este tipo."""
    try:
        from app.database import db
        from app.models.notification_prefs import NotificationPrefs
        prefs = db.session.query(NotificationPrefs).filter_by(user_id=user_id).first()
        if prefs is None:
            return True  # por defecto habilitado
        campo = f"{tipo}_mail"
        return bool(getattr(prefs, campo, True))
    except Exception:
        return True


def enviar_mail(destinatario_email, asunto, cuerpo_html, user_id=None, tipo=None):
    """
    Envía un email si las preferencias del usuario lo permiten.
    Si MAIL_USERNAME no está configurado, no hace nada (modo desarrollo).
    """
    if not current_app.config.get("MAIL_USERNAME"):
        return  # sin credenciales, ignorar silenciosamente

    if user_id and tipo and not _prefs_allow(user_id, tipo):
        return  # el usuario desactivó este tipo de mail

    try:
        msg = Message(
            subject=asunto,
            recipients=[destinatario_email],
            html=cuerpo_html,
        )
        mail.send(msg)
    except Exception as e:
        current_app.logger.warning(f"[mail] Error al enviar a {destinatario_email}: {e}")


# ── Templates de mail ─────────────────────────────────────────────

def _base_html(contenido: str) -> str:
    return f"""
    <div style="font-family:'Helvetica Neue',Arial,sans-serif;max-width:520px;margin:0 auto;background:#F7F3EE;padding:32px 16px;">
      <div style="background:#fff;border-radius:16px;overflow:hidden;border:1px solid #E7DED2;">
        <div style="background:#FF6B35;padding:20px 28px;">
          <span style="font-size:1.5rem;font-weight:900;color:#fff;font-style:italic;letter-spacing:-0.02em;">Morfi</span>
        </div>
        <div style="padding:28px;">
          {contenido}
        </div>
        <div style="padding:16px 28px;border-top:1px solid #F0EBE3;text-align:center;font-size:0.75rem;color:#8C8593;">
          © Morfi · <a href="#" style="color:#FF6B35;text-decoration:none;">Gestionar notificaciones</a>
        </div>
      </div>
    </div>
    """


def mail_reserva_confirmada(usuario_email, usuario_nombre, restaurante_nombre, fecha_hora, user_id):
    """Mail que se envía al usuario cuando su reserva queda confirmada."""
    cuerpo = _base_html(f"""
        <h2 style="color:#1A1A2E;margin:0 0 8px;">¡Reserva confirmada! 🎉</h2>
        <p style="color:#5C544E;">Hola <strong>{usuario_nombre}</strong>, tu reserva en <strong>{restaurante_nombre}</strong> está confirmada.</p>
        <div style="background:#F7F3EE;border-radius:12px;padding:16px;margin:20px 0;">
          <p style="margin:0;color:#1A1A2E;font-weight:700;">📅 {fecha_hora}</p>
        </div>
        <p style="color:#5C544E;">Acordate de llegar a horario. ¡Que lo disfrutes!</p>
    """)
    enviar_mail(usuario_email, f"Reserva confirmada en {restaurante_nombre}", cuerpo, user_id=user_id, tipo="reserva")


def mail_respuesta_resena(usuario_email, usuario_nombre, restaurante_nombre, respuesta_texto, user_id):
    """Mail cuando el restaurante responde la reseña del usuario."""
    cuerpo = _base_html(f"""
        <h2 style="color:#1A1A2E;margin:0 0 8px;">El restaurante respondió tu reseña 💬</h2>
        <p style="color:#5C544E;">Hola <strong>{usuario_nombre}</strong>, <strong>{restaurante_nombre}</strong> respondió tu reseña:</p>
        <div style="background:#F7F3EE;border-radius:12px;padding:16px;margin:20px 0;border-left:3px solid #FF6B35;">
          <p style="margin:0;color:#1A1A2E;font-style:italic;">"{respuesta_texto}"</p>
        </div>
    """)
    enviar_mail(usuario_email, f"{restaurante_nombre} respondió tu reseña", cuerpo, user_id=user_id, tipo="respuesta")


def mail_solicitud_amistad(usuario_email, usuario_nombre, solicitante_nombre, user_id):
    """Mail cuando alguien envía solicitud de amistad."""
    cuerpo = _base_html(f"""
        <h2 style="color:#1A1A2E;margin:0 0 8px;">Nueva solicitud de amistad 👋</h2>
        <p style="color:#5C544E;">Hola <strong>{usuario_nombre}</strong>, <strong>{solicitante_nombre}</strong> te envió una solicitud de amistad en Morfi.</p>
        <p style="color:#5C544E;">Entrá a la app para aceptarla.</p>
    """)
    enviar_mail(usuario_email, f"{solicitante_nombre} quiere ser tu amigo en Morfi", cuerpo, user_id=user_id, tipo="amistad")