import uuid

from sqlalchemy.dialects.postgresql import UUID

from app.database import db
from app.models.enums import BeneficioValorTipo, CondicionTipo


class Beneficio(db.Model):
    """Beneficio de fidelidad para comensales frecuentes de un restaurante.

    El comensal accede al beneficio cuando cumple la condición (ej. 5 visitas
    completadas). El valor se expresa como porcentaje o monto fijo.
    """

    __tablename__ = "Beneficio"

    id = db.Column("Id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    id_restaurante = db.Column(
        "IdRestaurante",
        UUID(as_uuid=True),
        db.ForeignKey("Restaurant.IdRestaurant"),
        nullable=False,
    )
    descripcion = db.Column("Descripcion", db.Text, nullable=False)
    tipo_condicion = db.Column(
        "TipoCondicion",
        db.Enum(CondicionTipo, name="beneficio_condicion_tipo"),
        nullable=False,
        default=CondicionTipo.VISITAS,
    )
    valor_condicion = db.Column("ValorCondicion", db.Integer, nullable=False)
    tipo_beneficio = db.Column(
        "TipoBeneficio",
        db.Enum(BeneficioValorTipo, name="beneficio_valor_tipo"),
        nullable=False,
    )
    valor_beneficio = db.Column("ValorBeneficio", db.Numeric(10, 2), nullable=False)
    activo = db.Column("Activo", db.Boolean, nullable=False, default=True)
    created_at = db.Column(
        "CreatedAt",
        db.DateTime(timezone=True),
        nullable=False,
        server_default=db.func.now(),
    )

    restaurant = db.relationship("Restaurant", back_populates="beneficios")