# models.py
from datetime import datetime
from db_init import db  # Changed from 'from db_init import db'
from flask_login import UserMixin

# Define machine learning model type enum
class MLModelType:
    ENSEMBLE = 'ensemble'
    NEURAL_NETWORK = 'neural_network'
    RULE_BASED = 'rule_based'

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.Text)
    gmail_access_token = db.Column(db.Text)
    gmail_refresh_token = db.Column(db.Text)
    gmail_token_expiry = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    
    # Relationships
    emails = db.relationship('Email', backref='user', lazy=True)
    progress = db.relationship('UserProgress', backref='user', lazy=True, uselist=False)

    @staticmethod
    def _get_cipher():
        import os
        import base64
        from cryptography.fernet import Fernet
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
        
        secret = (os.environ.get("SESSION_SECRET") or os.environ.get("SECRET_KEY") or "default_dev_secret_key").encode()
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b"email_intelligence_salt",
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(secret))
        return Fernet(key)

    def set_access_token(self, token):
        """Encrypt and store access token."""
        if not token:
            self.gmail_access_token = None
            return
        cipher = self._get_cipher()
        self.gmail_access_token = cipher.encrypt(token.encode()).decode()

    def get_access_token(self):
        """Decrypt and return access token."""
        if not self.gmail_access_token:
            return None
        try:
            cipher = self._get_cipher()
            return cipher.decrypt(self.gmail_access_token.encode()).decode()
        except Exception:
            return self.gmail_access_token  # Fallback for plain tokens

    def set_refresh_token(self, token):
        """Encrypt and store refresh token."""
        if not token:
            self.gmail_refresh_token = None
            return
        cipher = self._get_cipher()
        self.gmail_refresh_token = cipher.encrypt(token.encode()).decode()

    def get_refresh_token(self):
        """Decrypt and return refresh token."""
        if not self.gmail_refresh_token:
            return None
        try:
            cipher = self._get_cipher()
            return cipher.decrypt(self.gmail_refresh_token.encode()).decode()
        except Exception:
            return self.gmail_refresh_token  # Fallback for plain tokens

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

class PhishingClassification(db.Model):
    """Model to store phishing detection results for emails"""
    id = db.Column(db.Integer, primary_key=True)
    email_id = db.Column(db.Integer, db.ForeignKey('email.id'), nullable=False, unique=True)
    phishing_score = db.Column(db.Float, nullable=False)  # Probability score (0-1)
    is_phishing = db.Column(db.Boolean, default=False)
    model_type = db.Column(db.String(32), default=MLModelType.ENSEMBLE)
    features_json = db.Column(db.Text)  # Store features as JSON
    feedback = db.Column(db.Boolean, nullable=True)  # User feedback (True=phishing, False=not phishing, None=no feedback)
    classified_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationship
    email = db.relationship('Email', backref=db.backref('phishing_classification', uselist=False))
    
    def __repr__(self):
        return f'<PhishingClassification for email_id {self.email_id} score {self.phishing_score}>'