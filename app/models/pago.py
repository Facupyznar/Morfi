import uuid

from sqlalchemy.dialects.postgresql import UUID

from app.database import db


class Pago(db.Model):
    __tablename__ = "Pago"

    id = db.Column("Id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    id_reserva = db.Column("IdReserva", UUID(as_uuid=True), db.ForeignKey("Reserva.IdReserva"), nullable=False)
    preference_id = db.Column("PreferenceId", db.String(120))
    payment_id = db.Column("PaymentId", db.String(120))
    estado = db.Column("Estado", db.String(30), nullable=False, default="pendiente")
    monto = db.Column("Monto", db.Numeric(10, 2))
    created_at = db.Column("CreatedAt", db.DateTime(timezone=True), nullable=False, server_default=db.func.now())

    reserva = db.relationship("Reserva")
