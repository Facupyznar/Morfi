import uuid

from sqlalchemy.dialects.postgresql import UUID

from app.database import db


class Review(db.Model):
    __tablename__ = "Review"

    id_review = db.Column("IdReview", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    id_reserva = db.Column("IdReserva", UUID(as_uuid=True), db.ForeignKey("Reserva.IdReserva"), nullable=False, unique=True)
    comentario = db.Column("Comentario", db.Text)
    puntaje = db.Column("Puntaje", db.Integer, nullable=False)
    respuesta_socio = db.Column("Respuesta_socio", db.Text)

    reserva = db.relationship("Reserva", back_populates="review")
