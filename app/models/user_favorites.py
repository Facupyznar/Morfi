from sqlalchemy.dialects.postgresql import UUID

from app.database import db


class UserFavorites(db.Model):
    __tablename__ = "User_favorites"

    user_id = db.Column("UserID", UUID(as_uuid=True), db.ForeignKey("User.user_id"), primary_key=True)
    id_restaurante = db.Column("IdRestaurante", UUID(as_uuid=True), db.ForeignKey("Restaurant.IdRestaurant"), primary_key=True)
    fecha_agregado = db.Column("Fecha_agregado", db.DateTime(timezone=True), nullable=False, server_default=db.func.now())

    user = db.relationship("User", foreign_keys=[user_id], backref=db.backref("favorite_restaurants", lazy=True, cascade="all, delete-orphan"))
    restaurant = db.relationship("Restaurant", back_populates="favoritos")
