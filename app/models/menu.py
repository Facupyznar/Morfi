import uuid

from sqlalchemy.dialects.postgresql import UUID

from app.database import db


class Menu(db.Model):
    __tablename__ = "Menu"

    id_plato = db.Column("IdPlato", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    id_restaurant = db.Column("IdRestaurant", UUID(as_uuid=True), db.ForeignKey("Restaurant.IdRestaurant"), nullable=False)
    nombre = db.Column("Nombre", db.String(150), nullable=False)
    precio = db.Column("Precio", db.Numeric(10, 2), nullable=False)
    descripcion = db.Column("Descripcion", db.Text)
    categoria = db.Column("Categoria", db.String(50))
    disponibilidad = db.Column("Disponibilidad", db.Boolean, nullable=False, default=True)

    restaurant = db.relationship("Restaurant", back_populates="menus")
    menu_tags = db.relationship("MenuTags", back_populates="menu", cascade="all, delete-orphan", lazy=True)
    beneficio_platos = db.relationship("BeneficioPlato", back_populates="menu", cascade="all, delete-orphan", lazy=True)
