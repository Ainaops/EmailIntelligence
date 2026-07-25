# app.py
import os
import secrets
import logging
from flask import Flask, render_template, redirect, url_for, flash, request
from flask_login import LoginManager, current_user, login_required
from werkzeug.middleware.proxy_fix import ProxyFix

# Configure logging
logging.basicConfig(level=logging.DEBUG)

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET") or secrets.token_hex(32)
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# Initialize database
from db_init import init_db
db = init_db(app)

# Initialize login manager
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "google_auth.login"

@login_manager.user_loader
def load_user(user_id):
    from models import User  # Import here to avoid circular import
    return User.query.get(int(user_id))

# Import and register blueprints
from google_auth import google_auth
from email_processor import email_processor_bp
from user_progress import user_progress_bp
from csv_exporter import csv_exporter_bp
from phishing_detector import phishing_detector_bp

app.register_blueprint(google_auth)
app.register_blueprint(email_processor_bp)
app.register_blueprint(user_progress_bp)
app.register_blueprint(csv_exporter_bp)
app.register_blueprint(phishing_detector_bp)

# Route for the home page
@app.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("email_processor_bp.dashboard"))
    return render_template("index.html")

# Health check endpoint for cloud monitoring (Render/AWS/K8s)
@app.route("/healthz")
def health():
    return "OK", 200

# Error handlers
@app.errorhandler(404)
def page_not_found(e):
    return render_template("base.html", error="404 - Page not found"), 404

@app.errorhandler(500)
def internal_server_error(e):
    return render_template("base.html", error="500 - Internal server error"), 500