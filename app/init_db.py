from app.database import db, ensure_menu_schema
from app.models import ModelUser, User
from app.run import app


with app.app_context():
    db.create_all()
    ensure_menu_schema()
