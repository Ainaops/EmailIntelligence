from datetime import datetime
from app import db
from flask_login import UserMixin

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256))
    gmail_access_token = db.Column(db.String(256))
    gmail_refresh_token = db.Column(db.String(256))
    gmail_token_expiry = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    
    # Relationships
    emails = db.relationship('Email', backref='user', lazy=True)
    progress = db.relationship('UserProgress', backref='user', lazy=True, uselist=False)

    def __repr__(self):
        return f'<User {self.username}>'

class Email(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    message_id = db.Column(db.String(256), nullable=False)
    sender = db.Column(db.String(120), nullable=False)
    sender_name = db.Column(db.String(120))
    recipient = db.Column(db.String(120), nullable=False)
    subject = db.Column(db.String(512))
    body_text = db.Column(db.Text)
    body_html = db.Column(db.Text)
    body_cleaned = db.Column(db.Text)
    date_received = db.Column(db.DateTime)
    date_processed = db.Column(db.DateTime, default=datetime.utcnow)
    is_read = db.Column(db.Boolean, default=False)
    
    def __repr__(self):
        return f'<Email {self.subject}>'

class UserProgress(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), unique=True, nullable=False)
    total_emails_processed = db.Column(db.Integer, default=0)
    last_email_processed = db.Column(db.DateTime)
    last_sync_date = db.Column(db.DateTime)
    emails_read = db.Column(db.Integer, default=0)
    favorite_senders = db.Column(db.Text)  # Store as JSON
    
    def __repr__(self):
        return f'<UserProgress for user_id {self.user_id}>'
