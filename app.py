import os
import logging

from flask import Flask, render_template, redirect, url_for, flash, request
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, current_user, login_required
from sqlalchemy.orm import DeclarativeBase
from werkzeug.middleware.proxy_fix import ProxyFix

# Configure logging
logging.basicConfig(level=logging.DEBUG)

class Base(DeclarativeBase):
    pass

# Initialize Flask and SQLAlchemy
db = SQLAlchemy(model_class=Base)
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET")
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# Configure database
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///email_processor.db")
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Initialize database
db.init_app(app)

# Initialize login manager
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "google_auth.login"

@login_manager.user_loader
def load_user(user_id):
    from models import User
    return User.query.get(int(user_id))

# Create database tables
with app.app_context():
    from models import User, Email, UserProgress
    db.create_all()

# Import and register blueprints
from google_auth import google_auth
from email_processor import email_processor_bp
from user_progress import user_progress_bp
from csv_exporter import csv_exporter_bp

app.register_blueprint(google_auth)
app.register_blueprint(email_processor_bp)
app.register_blueprint(user_progress_bp)
app.register_blueprint(csv_exporter_bp)

# Route for the home page
@app.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("email_processor_bp.dashboard"))
    return render_template("index.html")

# Error handlers
@app.errorhandler(404)
def page_not_found(e):
    return render_template("base.html", error="404 - Page not found"), 404

@app.errorhandler(500)
def internal_server_error(e):
    return render_template("base.html", error="500 - Internal server error"), 500
