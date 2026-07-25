import json
import os
import logging
from datetime import datetime, timedelta

import requests
from db_init import db
from flask import Blueprint, redirect, request, url_for, flash, session
from flask_login import login_required, login_user, logout_user, current_user
from models import User, UserProgress
from oauthlib.oauth2 import WebApplicationClient

logger = logging.getLogger(__name__)

# Get OAuth credentials from environment variables
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_OAUTH_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET")
GOOGLE_DISCOVERY_URL = "https://accounts.google.com/.well-known/openid-configuration"

# Log credential status at startup (without revealing the actual values)
if not GOOGLE_CLIENT_ID:
    logger.warning("GOOGLE_OAUTH_CLIENT_ID is not set")
if not GOOGLE_CLIENT_SECRET:
    logger.warning("GOOGLE_OAUTH_CLIENT_SECRET is not set")
else:
    logger.info("Google OAuth credentials are configured")

# Make sure to use this redirect URL. It has to match the one in the whitelist
DEV_REDIRECT_URL = 'https://abfb-105-113-91-56.ngrok-free.app/google_login/callback'

client = WebApplicationClient(GOOGLE_CLIENT_ID)

google_auth = Blueprint("google_auth", __name__)

@google_auth.route("/google_login")
def login():
    # Check if client ID and secret are set
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        flash("Google OAuth credentials not configured", "danger")
        return redirect(url_for("index"))
        
    # Get Google's OAuth 2.0 endpoints
    try:
        google_provider_cfg = requests.get(GOOGLE_DISCOVERY_URL).json()
        authorization_endpoint = google_provider_cfg["authorization_endpoint"]

        # Use the library to construct the request for Google login
        # Use the predefined redirect URL that matches what's in Google Cloud Console
        redirect_uri = DEV_REDIRECT_URL
        
        request_uri = client.prepare_request_uri(
            authorization_endpoint,
            redirect_uri=redirect_uri,
            scope=["openid", "email", "profile", "https://mail.google.com/"],
        )
        
        logger.debug(f"Redirecting to: {request_uri}")
        return redirect(request_uri)
    except Exception as e:
        logger.error(f"Error during Google login: {str(e)}")
        flash("Failed to connect to Google authentication service", "danger")
        return redirect(url_for("index"))

@google_auth.route("/google_login/callback")
def callback():
    # Get authorization code from request
    code = request.args.get("code")
    if not code:
        flash("Authentication failed: No authorization code received", "danger")
        return redirect(url_for("index"))
    
    try:
        # Get Google's token endpoint
        google_provider_cfg = requests.get(GOOGLE_DISCOVERY_URL).json()
        token_endpoint = google_provider_cfg["token_endpoint"]

        # Prepare and send token request
        # Use the predefined redirect URL that matches what's in Google Cloud Console
        redirect_uri = DEV_REDIRECT_URL
        
        # Log debugging information
        logger.debug(f"Authorization code: {code}")
        logger.debug(f"Redirect URI: {redirect_uri}")
        logger.debug(f"Client ID is set: {bool(GOOGLE_CLIENT_ID)}")
        logger.debug(f"Client Secret is set: {bool(GOOGLE_CLIENT_SECRET)}")
        
        token_url, headers, body = client.prepare_token_request(
            token_endpoint,
            authorization_response=request.url.replace("http://", "https://"),
            redirect_url=redirect_uri,
            code=code,
        )
        
        # Log request details
        logger.debug(f"Token URL: {token_url}")
        logger.debug(f"Request body: {body}")
        
        # Make sure client credentials are not None
        if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
            logger.error("Google OAuth credentials missing")
            flash("Authentication failed: OAuth credentials not configured", "danger")
            return redirect(url_for("index"))
            
        # Create a tuple for auth only if both values are present
        auth = None
        if GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET:
            auth = (GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET)
        else:
            raise ValueError("Google OAuth credentials missing or invalid")
            
        token_response = requests.post(
            token_url,
            headers=headers,
            data=body,
            auth=auth,
        )
        
        # Log response information
        logger.debug(f"Token response status: {token_response.status_code}")
        if token_response.status_code != 200:
            error_msg = f"Token response error: {token_response.text}"
            logger.error(error_msg)
            raise ValueError(error_msg)

        # Parse the token response
        token_data = token_response.json()
        client.parse_request_body_response(json.dumps(token_data))

        # Get user info from Google
        userinfo_endpoint = google_provider_cfg["userinfo_endpoint"]
        uri, headers, body = client.add_token(userinfo_endpoint)
        userinfo_response = requests.get(uri, headers=headers, data=body)
        userinfo = userinfo_response.json()

        # Verify user email
        if not userinfo.get("email_verified"):
            flash("User email not verified by Google", "danger")
            return redirect(url_for("index"))

        # Extract user information
        users_email = userinfo["email"]
        users_name = userinfo.get("given_name", users_email.split("@")[0])
        
        # Check if user exists, otherwise create a new one
        user = User.query.filter_by(email=users_email).first()
        if not user:
            user = User(
                username=users_name,
                email=users_email,
                gmail_access_token=token_data.get("access_token"),
                gmail_refresh_token=token_data.get("refresh_token"),
                gmail_token_expiry=datetime.utcnow() + timedelta(seconds=token_data.get("expires_in", 3600)),
            )
            db.session.add(user)
            
            # Create user progress record
            progress = UserProgress(user=user)
            db.session.add(progress)
            db.session.commit()
            
            flash(f"Welcome, {users_name}! Your account has been created.", "success")
        else:
            # Update existing user's tokens
            user.gmail_access_token = token_data.get("access_token")
            if token_data.get("refresh_token"):
                user.gmail_refresh_token = token_data.get("refresh_token")
            user.gmail_token_expiry = datetime.utcnow() + timedelta(seconds=token_data.get("expires_in", 3600))
            user.last_login = datetime.utcnow()
            db.session.commit()
            
            flash(f"Welcome back, {user.username}!", "success")

        # Log in the user
        login_user(user)
        
        # Store tokens in session for SMTP access
        session['access_token'] = token_data.get("access_token")
        
        # Redirect to dashboard
        return redirect(url_for("email_processor_bp.dashboard"))
    
    except Exception as e:
        logger.error(f"Error during Google callback: {str(e)}")
        flash("Authentication failed. Please try again.", "danger")
        return redirect(url_for("index"))

@google_auth.route("/logout")
@login_required
def logout():
    logout_user()
    # Clear session
    for key in list(session.keys()):
        session.pop(key)
    flash("You have been logged out successfully", "success")
    return redirect(url_for("index"))

@google_auth.route("/refresh_token")
@login_required
def refresh_token():
    """Refresh the Google access token"""
    if not current_user.gmail_refresh_token:
        flash("No refresh token available. Please re-authenticate.", "warning")
        return redirect(url_for("google_auth.login"))
    
    try:
        token_endpoint = requests.get(GOOGLE_DISCOVERY_URL).json()["token_endpoint"]
        
        # Verify that we have valid credentials
        if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
            logger.error("Missing Google OAuth credentials for token refresh")
            flash("OAuth credentials not configured properly", "danger")
            return redirect(url_for("google_auth.login"))
            
        refresh_data = {
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "refresh_token": current_user.gmail_refresh_token,
            "grant_type": "refresh_token"
        }
        
        logger.debug("Attempting to refresh access token")
        token_response = requests.post(token_endpoint, data=refresh_data)
        
        # Log response status for debugging
        logger.debug(f"Token refresh response status: {token_response.status_code}")
        token_data = token_response.json()
        
        if "access_token" in token_data:
            current_user.gmail_access_token = token_data["access_token"]
            current_user.gmail_token_expiry = datetime.utcnow() + timedelta(seconds=token_data.get("expires_in", 3600))
            db.session.commit()
            
            # Update session token
            session['access_token'] = token_data["access_token"]
            
            flash("Token refreshed successfully", "success")
        else:
            flash("Failed to refresh token. Please re-authenticate.", "warning")
            return redirect(url_for("google_auth.login"))
    
    except Exception as e:
        logger.error(f"Error refreshing token: {str(e)}")
        flash("Failed to refresh token. Please re-authenticate.", "warning")
        return redirect(url_for("google_auth.login"))
    
    return redirect(url_for("email_processor_bp.dashboard"))
