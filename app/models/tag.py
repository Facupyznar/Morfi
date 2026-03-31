import uuid

from sqlalchemy.dialects.postgresql import UUID

from app.database import db
from app.models.enums import TagCategory


class Tag(db.Model):
    __tablename__ = "Tag"

    id_tag = db.Column("IdTag", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = db.Column("Name", db.String(50), nullable=False, unique=True)
    category = db.Column("Category", db.Enum(TagCategory, name="tag_category"), nullable=False)

    user_tags = db.relationship("UserTags", back_populates="tag", cascade="all, delete-orphan", lazy=True)
    menu_tags = db.relationship("MenuTags", back_populates="tag", cascade="all, delete-orphan", lazy=True)
