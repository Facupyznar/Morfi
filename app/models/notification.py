import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy.dialects.postgresql import UUID

from app.database import db


class Notification(db.Model):
    __tablename__ = "notifications"

    id_notification = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id         = db.Column(UUID(as_uuid=True), nullable=False, index=True)
    tipo            = db.Column(String(50), nullable=False)   # review, reserva, respuesta, amistad, beneficio
    titulo          = db.Column(String(200), nullable=False)
    descripcion     = db.Column(Text, nullable=True)
    leida           = db.Column(Boolean, default=False, nullable=False)
    fecha           = db.Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    url_destino     = db.Column(String(500), nullable=True)