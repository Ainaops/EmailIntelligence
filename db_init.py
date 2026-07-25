# db_init.py
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass

# Initialize SQLAlchemy without binding to an app yet
db = SQLAlchemy(model_class=Base)

def init_db(app):
    """Initialize the database with the Flask app."""
    app.config["SQLALCHEMY_DATABASE_URI"] = app.config.get("SQLALCHEMY_DATABASE_URI", "sqlite:///email_intelligence.db")
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "pool_recycle": 300,
        "pool_pre_ping": True,
    }
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)
    
    # Import models here to avoid circular imports
    from models import User, Email, UserProgress, PhishingClassification
    
    with app.app_context():
        db.create_all()
    
    return db