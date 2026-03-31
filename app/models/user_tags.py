from sqlalchemy.dialects.postgresql import UUID

from app.database import db


class UserTags(db.Model):
    __tablename__ = "User_tags"

    user_id = db.Column("UserID", UUID(as_uuid=True), db.ForeignKey("User.user_id"), primary_key=True)
    id_tag = db.Column("IdTag", UUID(as_uuid=True), db.ForeignKey("Tag.IdTag"), primary_key=True)

    user = db.relationship("User", foreign_keys=[user_id], backref=db.backref("user_tags", lazy=True, cascade="all, delete-orphan"))
    tag = db.relationship("Tag", back_populates="user_tags")
