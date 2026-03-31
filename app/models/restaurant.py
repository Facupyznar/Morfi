import uuid

from geoalchemy2 import Geometry
from sqlalchemy.dialects.postgresql import UUID

from app.database import db
from app.models.enums import RestaurantStatus


class Restaurant(db.Model):
    __tablename__ = "Restaurant"

    id_restaurant = db.Column("IdRestaurant", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    id_socio_admin = db.Column("IdSocioAdmin", UUID(as_uuid=True), db.ForeignKey("User.user_id"), nullable=False)
    name = db.Column("Name", db.String(100), nullable=False)
    ubicacion = db.Column("Ubicacion", Geometry("POINT", srid=4326), nullable=False)
    capacidad = db.Column("Capacidad", db.Integer, nullable=False)
    puntaje = db.Column("Puntaje", db.Numeric(3, 2), nullable=False, default=0)
    horario = db.Column("Horario", db.Text)
    estado = db.Column("Estado", db.Enum(RestaurantStatus, name="restaurant_status"), nullable=False, default=RestaurantStatus.ACTIVO)

    socio_admin = db.relationship("User", foreign_keys=[id_socio_admin], backref=db.backref("restaurants_admin", lazy=True))
    menus = db.relationship("Menu", back_populates="restaurant", cascade="all, delete-orphan", lazy=True)
    reservas = db.relationship("Reserva", back_populates="restaurant", cascade="all, delete-orphan", lazy=True)
    beneficios = db.relationship("Beneficio", back_populates="restaurant", cascade="all, delete-orphan", lazy=True)
    favoritos = db.relationship("UserFavorites", back_populates="restaurant", cascade="all, delete-orphan", lazy=True)
