import uuid

from sqlalchemy.dialects.postgresql import UUID

from app.database import db
from app.models.enums import FriendshipStatus


class Friends(db.Model):
    __tablename__ = "Friends"

    id_amistad = db.Column("IdAmistad", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id_1 = db.Column("UserId_1", UUID(as_uuid=True), db.ForeignKey("User.user_id"), nullable=False)
    user_id_2 = db.Column("UserId_2", UUID(as_uuid=True), db.ForeignKey("User.user_id"), nullable=False)
    estado = db.Column("Estado", db.Enum(FriendshipStatus, name="friendship_status"), nullable=False, default=FriendshipStatus.PENDIENTE)
    fecha = db.Column("Fecha", db.DateTime(timezone=True), nullable=False, server_default=db.func.now())

    user_1 = db.relationship("User", foreign_keys=[user_id_1], backref=db.backref("friendships_sent", lazy=True))
    user_2 = db.relationship("User", foreign_keys=[user_id_2], backref=db.backref("friendships_received", lazy=True))
