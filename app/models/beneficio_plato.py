from sqlalchemy.dialects.postgresql import UUID

from app.database import db


class BeneficioPlato(db.Model):
    __tablename__ = "Beneficio_plato"

    id_oferta = db.Column("IdOferta", UUID(as_uuid=True), db.ForeignKey("Beneficio.IdOferta"), primary_key=True)
    id_plato = db.Column("IdPlato", UUID(as_uuid=True), db.ForeignKey("Menu.IdPlato"), primary_key=True)

    beneficio = db.relationship("Beneficio", back_populates="beneficio_platos")
    menu = db.relationship("Menu", back_populates="beneficio_platos")
