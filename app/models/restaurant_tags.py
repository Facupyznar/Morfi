from sqlalchemy.dialects.postgresql import UUID

from app.database import db


class RestaurantTags(db.Model):
    __tablename__ = "Restaurant_tags"

    id_restaurant = db.Column("IdRestaurant", UUID(as_uuid=True), db.ForeignKey("Restaurant.IdRestaurant"), primary_key=True)
    id_tag = db.Column("IdTag", UUID(as_uuid=True), db.ForeignKey("Tag.IdTag"), primary_key=True)

    restaurant = db.relationship(
        "Restaurant",
        foreign_keys=[id_restaurant],
        back_populates="restaurant_tags",
    )
    tag = db.relationship("Tag", back_populates="restaurant_tags")
