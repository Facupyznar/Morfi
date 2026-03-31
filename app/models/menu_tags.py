from sqlalchemy.dialects.postgresql import UUID

from app.database import db


class MenuTags(db.Model):
    __tablename__ = "Menu_tags"

    id_plato = db.Column("IdPlato", UUID(as_uuid=True), db.ForeignKey("Menu.IdPlato"), primary_key=True)
    id_tag = db.Column("IdTag", UUID(as_uuid=True), db.ForeignKey("Tag.IdTag"), primary_key=True)

    menu = db.relationship("Menu", back_populates="menu_tags")
    tag = db.relationship("Tag", back_populates="menu_tags")
