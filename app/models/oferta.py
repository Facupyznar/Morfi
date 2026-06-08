import uuid

from sqlalchemy.dialects.postgresql import UUID

from app.database import db


class Oferta(db.Model):
    """Oferta temporal de un restaurante, vigente entre fecha_inicio y fecha_fin."""

    __tablename__ = "Oferta"

    id = db.Column("Id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    id_restaurante = db.Column(
        "IdRestaurante",
        UUID(as_uuid=True),
        db.ForeignKey("Restaurant.IdRestaurant"),
        nullable=False,
    )
    titulo = db.Column("Titulo", db.String(120), nullable=False)
    descripcion = db.Column("Descripcion", db.Text, nullable=True)
    imagen_path = db.Column("ImagenPath", db.String(255), nullable=True)
    fecha_inicio = db.Column("FechaInicio", db.DateTime(timezone=True), nullable=False)
    fecha_fin = db.Column("FechaFin", db.DateTime(timezone=True), nullable=False)
    activo = db.Column("Activo", db.Boolean, nullable=False, default=True)
    created_at = db.Column(
        "CreatedAt",
        db.DateTime(timezone=True),
        nullable=False,
        server_default=db.func.now(),
    )

    restaurant = db.relationship("Restaurant", back_populates="ofertas")
