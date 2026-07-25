"""
Google OAuth 2.0 Authentication & Session Management Module
Refactored for enterprise code quality, separation of concerns, and security.
"""

import json
import os
import logging
from datetime import datetime, timedelta
from functools import lru_cache

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from flask import Blueprint, redirect, request, url_for, flash, session
from flask_login import login_required, login_user, logout_user, current_user
from oauthlib.oauth2 import WebApplicationClient, OAuth2Error
from sqlalchemy.exc import SQLAlchemyError

from db_init import db
from models import User, UserProgress

logger = logging.getLogger(__name__)

# ==============================================================================
# 🛠️ Configuration & Constants
# ==============================================================================

class OAuthConfig:
    """Centralized configuration and credential validator for Google OAuth."""
    CLIENT_ID = os.environ.get("GOOGLE_OAUTH_CLIENT_ID")
    CLIENT_SECRET = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET")
    REDIRECT_URI = os.environ.get(
        "GOOGLE_REDIRECT_URI",
        "https://abfb-105-113-91-56.ngrok-free.app/google_login/callback"
    )
    DISCOVERY_URL = "https://accounts.google.com/.well-known/openid-configuration"
    SCOPES = ["openid", "email", "profile", "https://mail.google.com/"]
    HTTP_TIMEOUT = 10  # Seconds

    @classmethod
    def validate(cls):
        """Validate that essential OAuth environment variables are present."""
        if not cls.CLIENT_ID or not cls.CLIENT_SECRET:
            logger.warning("Google OAuth credentials (CLIENT_ID / CLIENT_SECRET) are missing.")
            return False
        return True

SESSION_ACCESS_TOKEN_KEY = "access_token"

# Log credential status on module load
if not OAuthConfig.validate():
    logger.warning("Google OAuth credentials are not fully configured.")
else:
    logger.info("Google OAuth credentials initialized successfully.")

google_auth = Blueprint("google_auth", __name__)


# ==============================================================================
# 🌐 HTTP Session Client with Retry Logic & Discovery Caching
# ==============================================================================

def get_http_session():
    """Create a requests Session equipped with automatic retry strategy."""
    http = requests.Session()
    retries = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[500, 502, 503, 504],
        raise_on_status=False
    )
    adapter = HTTPAdapter(max_retries=retries)
    http.mount("https://", adapter)
    http.mount("http://", adapter)
    return http

@lru_cache(maxsize=1)
def get_google_provider_cfg():
    """Fetch and cache Google's OpenID Connect discovery configuration."""
    session_http = get_http_session()
    response = session_http.get(OAuthConfig.DISCOVERY_URL, timeout=OAuthConfig.HTTP_TIMEOUT)
    response.raise_for_status()
    return response.json()


# ==============================================================================
# 🔑 Google OAuth Client & Service Layer
# ==============================================================================

class GoogleOAuthService:
    """Encapsulates Google OAuth2 API interactions."""

    def __init__(self):
        self.client = WebApplicationClient(OAuthConfig.CLIENT_ID) if OAuthConfig.CLIENT_ID else None

    def get_authorization_url(self, redirect_uri):
        """Construct the Google OAuth authorization URL."""
        if not OAuthConfig.validate() or not self.client:
            raise ValueError("Google OAuth credentials not configured.")
        
        cfg = get_google_provider_cfg()
        auth_endpoint = cfg["authorization_endpoint"]
        request_uri = self.client.prepare_request_uri(
            auth_endpoint,
            redirect_uri=redirect_uri,
            scope=OAuthConfig.SCOPES,
        )
        return request_uri

    def exchange_code_for_tokens(self, code, authorization_response, redirect_uri):
        """Exchange authorization code for OAuth access and refresh tokens."""
        if not OAuthConfig.validate() or not self.client:
            raise ValueError("Google OAuth credentials missing or invalid.")

        cfg = get_google_provider_cfg()
        token_endpoint = cfg["token_endpoint"]

        token_url, headers, body = self.client.prepare_token_request(
            token_endpoint,
            authorization_response=authorization_response,
            redirect_url=redirect_uri,
            code=code,
        )

        session_http = get_http_session()
        token_response = session_http.post(
            token_url,
            headers=headers,
            data=body,
            auth=(OAuthConfig.CLIENT_ID, OAuthConfig.CLIENT_SECRET),
            timeout=OAuthConfig.HTTP_TIMEOUT
        )

        if token_response.status_code != 200:
            logger.error(f"Google token response status: {token_response.status_code}")
            raise ValueError("Failed to retrieve access token from Google.")

        token_data = token_response.json()
        self.client.parse_request_body_response(json.dumps(token_data))
        return token_data

    def fetch_user_profile(self):
        """Fetch authenticated user's Google profile using active token."""
        cfg = get_google_provider_cfg()
        userinfo_endpoint = cfg["userinfo_endpoint"]

        uri, headers, body = self.client.add_token(userinfo_endpoint)
        session_http = get_http_session()
        userinfo_response = session_http.get(
            uri,
            headers=headers,
            data=body,
            timeout=OAuthConfig.HTTP_TIMEOUT
        )

        if userinfo_response.status_code != 200:
            raise ValueError("Failed to fetch user profile from Google.")

        userinfo = userinfo_response.json()
        if not userinfo.get("email_verified"):
            raise ValueError("Google user email is not verified.")

        return userinfo

    def refresh_access_token(self, refresh_token):
        """Refresh an expired OAuth access token using a refresh token."""
        if not OAuthConfig.validate():
            raise ValueError("Google OAuth credentials not configured.")

        cfg = get_google_provider_cfg()
        token_endpoint = cfg["token_endpoint"]

        refresh_data = {
            "client_id": OAuthConfig.CLIENT_ID,
            "client_secret": OAuthConfig.CLIENT_SECRET,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token"
        }

        session_http = get_http_session()
        response = session_http.post(
            token_endpoint,
            data=refresh_data,
            timeout=OAuthConfig.HTTP_TIMEOUT
        )

        if response.status_code != 200:
            raise ValueError("Token refresh request failed.")

        token_data = response.json()
        if "access_token" not in token_data:
            raise ValueError("Response missing new access token.")

        return token_data


# ==============================================================================
# 👤 User Database Service
# ==============================================================================

class UserService:
    """Manages User model creation and database synchronization."""

    @staticmethod
    def get_or_create_user(profile_data, token_data):
        """Retrieve existing user or create a new user account atomically."""
        email = profile_data["email"]
        name = profile_data.get("given_name", email.split("@")[0])
        expires_in = token_data.get("expires_in", 3600)
        token_expiry = datetime.utcnow() + timedelta(seconds=expires_in)

        user = User.query.filter_by(email=email).first()
        is_new_user = False

        if not user:
            is_new_user = True
            user = User(
                username=name,
                email=email,
                gmail_access_token=token_data.get("access_token"),
                gmail_refresh_token=token_data.get("refresh_token"),
                gmail_token_expiry=token_expiry,
                last_login=datetime.utcnow()
            )
            db.session.add(user)
            progress = UserProgress(user=user)
            db.session.add(progress)
        else:
            user.gmail_access_token = token_data.get("access_token")
            if token_data.get("refresh_token"):
                user.gmail_refresh_token = token_data.get("refresh_token")
            user.gmail_token_expiry = token_expiry
            user.last_login = datetime.utcnow()

        db.session.commit()
        return user, is_new_user

    @staticmethod
    def update_user_token(user, new_token_data):
        """Update an existing user's access token and expiry."""
        expires_in = new_token_data.get("expires_in", 3600)
        user.gmail_access_token = new_token_data["access_token"]
        user.gmail_token_expiry = datetime.utcnow() + timedelta(seconds=expires_in)
        db.session.commit()


# Helper to get active redirect URI dynamically
def get_redirect_uri():
    """Return configured redirect URI or dynamically generate fallback."""
    if OAuthConfig.REDIRECT_URI:
        return OAuthConfig.REDIRECT_URI
    return url_for("google_auth.callback", _external=True, _scheme="https")


# ==============================================================================
# 🔀 Flask Routes (Controllers)
# ==============================================================================

@google_auth.route("/google_login")
def login():
    """Initiate Google OAuth authentication flow."""
    if not OAuthConfig.validate():
        flash("Google OAuth credentials not configured.", "danger")
        return redirect(url_for("index"))

    try:
        oauth_service = GoogleOAuthService()
        redirect_uri = get_redirect_uri()
        request_uri = oauth_service.get_authorization_url(redirect_uri)
        return redirect(request_uri)

    except requests.RequestException as e:
        logger.error(f"Network error during Google login: {e}")
        flash("Failed to connect to Google authentication service.", "danger")
    except Exception as e:
        logger.error(f"Unexpected error during Google login: {e}")
        flash("Authentication setup error occurred.", "danger")

    return redirect(url_for("index"))


@google_auth.route("/google_login/callback")
def callback():
    """Handle OAuth 2.0 callback response from Google."""
    code = request.args.get("code")
    if not code:
        flash("Authentication failed: Missing authorization code.", "danger")
        return redirect(url_for("index"))

    try:
        oauth_service = GoogleOAuthService()
        redirect_uri = get_redirect_uri()

        # 1. Exchange code for tokens
        auth_response_url = request.url.replace("http://", "https://")
        token_data = oauth_service.exchange_code_for_tokens(
            code=code,
            authorization_response=auth_response_url,
            redirect_uri=redirect_uri
        )

        # 2. Fetch user profile
        profile_data = oauth_service.fetch_user_profile()

        # 3. Create or update user atomically
        user, is_new = UserService.get_or_create_user(profile_data, token_data)

        # 4. Establish user session
        login_user(user)
        session[SESSION_ACCESS_TOKEN_KEY] = token_data.get("access_token")

        if is_new:
            flash(f"Welcome, {user.username}! Account created successfully.", "success")
        else:
            flash(f"Welcome back, {user.username}!", "success")

        return redirect(url_for("email_processor_bp.dashboard"))

    except requests.Timeout:
        logger.error("Timeout while communicating with Google OAuth servers.")
        flash("Authentication timed out. Please try again.", "danger")
    except requests.HTTPError as e:
        logger.error(f"HTTP error during OAuth callback: {e}")
        flash("Google authentication service error.", "danger")
    except (ValueError, OAuth2Error) as e:
        logger.error(f"OAuth validation error: {e}")
        flash("Authentication failed due to invalid response.", "danger")
    except SQLAlchemyError as e:
        db.session.rollback()
        logger.error(f"Database error saving user session: {e}")
        flash("Account creation failed due to database error.", "danger")
    except Exception as e:
        logger.error(f"Unexpected error during Google callback: {e}")
        flash("An unexpected authentication error occurred.", "danger")

    return redirect(url_for("index"))


@google_auth.route("/logout")
@login_required
def logout():
    """Log out current user and clear active session."""
    logout_user()
    session.clear()
    flash("You have been logged out successfully.", "success")
    return redirect(url_for("index"))


@google_auth.route("/refresh_token")
@login_required
def refresh_token():
    """Refresh the current user's Google OAuth access token."""
    if not current_user.gmail_refresh_token:
        flash("No refresh token available. Please re-authenticate.", "warning")
        return redirect(url_for("google_auth.login"))

    try:
        oauth_service = GoogleOAuthService()
        token_data = oauth_service.refresh_access_token(current_user.gmail_refresh_token)

        UserService.update_user_token(current_user, token_data)
        session[SESSION_ACCESS_TOKEN_KEY] = token_data["access_token"]

        flash("Access token refreshed successfully.", "success")
        return redirect(url_for("email_processor_bp.dashboard"))

    except requests.RequestException as e:
        logger.error(f"Network error refreshing token: {e}")
        flash("Network failure while refreshing token.", "warning")
    except (ValueError, SQLAlchemyError) as e:
        db.session.rollback()
        logger.error(f"Failed to refresh token: {e}")
        flash("Failed to refresh token. Please re-authenticate.", "warning")

    return redirect(url_for("google_auth.login"))
