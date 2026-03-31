import uuid

from sqlalchemy.dialects.postgresql import UUID

from app.database import db
from app.models.enums import ReservaStatus


class Reserva(db.Model):
    __tablename__ = "Reserva"

    id_reserva = db.Column("IdReserva", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = db.Column("UserID", UUID(as_uuid=True), db.ForeignKey("User.user_id"), nullable=False)
    id_restaurant = db.Column("IdRestaurant", UUID(as_uuid=True), db.ForeignKey("Restaurant.IdRestaurant"), nullable=False)
    fecha_hora = db.Column("Fecha_hora", db.DateTime(timezone=True), nullable=False)
    cant_personas = db.Column("Cant_personas", db.Integer, nullable=False)
    estado_reserva = db.Column("Estado_reserva", db.Enum(ReservaStatus, name="reserva_status"), nullable=False, default=ReservaStatus.PENDIENTE)
    token_validacion = db.Column("Token_validacion", db.String(150), unique=True)

    user = db.relationship("User", foreign_keys=[user_id], backref=db.backref("reservas", lazy=True))
    restaurant = db.relationship("Restaurant", back_populates="reservas")
    review = db.relationship("Review", back_populates="reserva", uselist=False, cascade="all, delete-orphan")
