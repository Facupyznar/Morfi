import uuid

from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import Boolean

from app.database import db


class NotificationPrefs(db.Model):
    __tablename__ = "notification_prefs"

    id          = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id     = db.Column(UUID(as_uuid=True), nullable=False, unique=True, index=True)

    # Reseñas de amigos
    review_inapp  = db.Column(Boolean, default=True, nullable=False)
    review_mail   = db.Column(Boolean, default=True, nullable=False)

    # Respuestas a tus reseñas
    respuesta_inapp = db.Column(Boolean, default=True, nullable=False)
    respuesta_mail  = db.Column(Boolean, default=True, nullable=False)

    # Reservas
    reserva_inapp = db.Column(Boolean, default=True, nullable=False)
    reserva_mail  = db.Column(Boolean, default=True, nullable=False)

    # Beneficios y ofertas
    beneficio_inapp = db.Column(Boolean, default=True,  nullable=False)
    beneficio_mail  = db.Column(Boolean, default=False, nullable=False)

    # Solicitudes de amistad
    amistad_inapp = db.Column(Boolean, default=True,  nullable=False)
    amistad_mail  = db.Column(Boolean, default=False, nullable=False)

    @classmethod
    def get_or_create(cls, db_session, user_id):
        prefs = db_session.query(cls).filter_by(user_id=user_id).first()
        if prefs is None:
            prefs = cls(user_id=user_id)
            db_session.add(prefs)
            db_session.commit()
        return prefs