import uuid

from sqlalchemy.dialects.postgresql import UUID

from app.database import db
from app.models.enums import BeneficioAplicaA, BeneficioTipo


class Beneficio(db.Model):
    __tablename__ = "Beneficio"

    id_oferta = db.Column("IdOferta", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    id_restaurant = db.Column("IdRestaurant", UUID(as_uuid=True), db.ForeignKey("Restaurant.IdRestaurant"), nullable=False)
    nivel_requerido = db.Column("Nivel_requerido", db.Integer, nullable=False)
    fecha_exp = db.Column("Fecha_exp", db.DateTime(timezone=True), nullable=False)
    tipo_beneficio = db.Column("Tipo_beneficio", db.Enum(BeneficioTipo, name="beneficio_tipo"), nullable=False)
    valor = db.Column("Valor", db.Numeric(10, 2), nullable=False)
    aplica_a = db.Column("Aplica_a", db.Enum(BeneficioAplicaA, name="beneficio_aplica_a"), nullable=False)

    restaurant = db.relationship("Restaurant", back_populates="beneficios")
    beneficio_platos = db.relationship("BeneficioPlato", back_populates="beneficio", cascade="all, delete-orphan", lazy=True)
