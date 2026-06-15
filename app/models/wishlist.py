import uuid

from sqlalchemy.dialects.postgresql import UUID

from app.database import db


class Wishlist(db.Model):
    """Lista nombrada de favoritos de un comensal (ej: "Románticos", "Con amigos").

    Los favoritos sin lista (``UserFavorites.wishlist_id`` en NULL) pertenecen a la
    lista por defecto "Guardados", que es virtual y no se persiste.
    """

    __tablename__ = "Wishlist"

    id = db.Column("Id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = db.Column("UserID", UUID(as_uuid=True), db.ForeignKey("User.user_id"), nullable=False)
    nombre = db.Column("Nombre", db.String(60), nullable=False)
    created_at = db.Column("Created_at", db.DateTime(timezone=True), nullable=False, server_default=db.func.now())

    user = db.relationship(
        "User",
        foreign_keys=[user_id],
        backref=db.backref("wishlists", lazy=True, cascade="all, delete-orphan"),
    )
    favoritos = db.relationship("UserFavorites", back_populates="wishlist", lazy=True)
