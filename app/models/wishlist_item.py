import uuid

from sqlalchemy.dialects.postgresql import UUID

from app.database import db


class WishlistItem(db.Model):
    __tablename__ = "Wishlist_item"

    id = db.Column("Id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    wishlist_id = db.Column("WishlistId", UUID(as_uuid=True), db.ForeignKey("Wishlist.Id", ondelete="CASCADE"), nullable=False)
    id_restaurante = db.Column("IdRestaurante", UUID(as_uuid=True), db.ForeignKey("Restaurant.IdRestaurant"), nullable=False)
    fecha_agregado = db.Column("Fecha_agregado", db.DateTime(timezone=True), nullable=False, server_default=db.func.now())

    __table_args__ = (
        db.UniqueConstraint("WishlistId", "IdRestaurante", name="uq_wishlist_item"),
    )

    wishlist = db.relationship("Wishlist", backref=db.backref("items", lazy=True, cascade="all, delete-orphan"))
    restaurant = db.relationship("Restaurant")
