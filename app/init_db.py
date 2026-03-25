from app.database import db
from app.models import ModelUser, User
from app.run import app


with app.app_context():
    db.create_all()
