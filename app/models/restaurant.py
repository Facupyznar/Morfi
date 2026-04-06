import uuid

from sqlalchemy.dialects.postgresql import UUID

from app.database import db
from app.models.enums import RestaurantStatus


class Restaurant(db.Model):
    __tablename__ = "Restaurant"

    id_restaurant = db.Column("IdRestaurant", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    id_owner = db.Column("IdOwner", UUID(as_uuid=True), db.ForeignKey("User.user_id"), nullable=False)
    name = db.Column("Name", db.String(100), nullable=False)
    address = db.Column("Address", db.String(255), nullable=False)
    latitude = db.Column("Latitude", db.Float, nullable=False)
    longitude = db.Column("Longitude", db.Float, nullable=False)
    capacidad = db.Column("Capacidad", db.Integer, nullable=False, default=0)
    puntaje = db.Column("Puntaje", db.Numeric(3, 2), nullable=False, default=0)
    horario = db.Column("Horario", db.Text)
    estado = db.Column("Estado", db.Enum(RestaurantStatus, name="restaurant_status"), nullable=False, default=RestaurantStatus.ACTIVO)

    owner = db.relationship("User", foreign_keys=[id_owner], backref=db.backref("owned_restaurants", lazy=True))
    restaurant_tags = db.relationship("RestaurantTags", back_populates="restaurant", cascade="all, delete-orphan", lazy=True)
    menus = db.relationship("Menu", back_populates="restaurant", cascade="all, delete-orphan", lazy=True)
    reservas = db.relationship("Reserva", back_populates="restaurant", cascade="all, delete-orphan", lazy=True)
    beneficios = db.relationship("Beneficio", back_populates="restaurant", cascade="all, delete-orphan", lazy=True)
    favoritos = db.relationship("UserFavorites", back_populates="restaurant", cascade="all, delete-orphan", lazy=True)
