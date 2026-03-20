from flask import Flask
from database import db, init_db
from config import Config
import os

from models.user import User


app = Flask(__name__)
app.config.from_object(Config)

init_db(app)


@app.route('/')
def home():
    return "Morfi App Iniciada y Conectada"



if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

