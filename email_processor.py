import imaplib
import email
import logging
import json
from datetime import datetime
from email.header import decode_header
from bs4 import BeautifulSoup

from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from app import db
from models import Email, UserProgress

# Configure logging
logger = logging.getLogger(__name__)

email_processor_bp = Blueprint('email_processor_bp', __name__)

def decode_mime_words(s):
    """Decode MIME encoded words in a string"""
    if s is None:
        return None
    
    try:
        decoded_parts = []
        for part, encoding in decode_header(s):
            if isinstance(part, bytes):
                if encoding:
                    decoded_parts.append(part.decode(encoding, errors='replace'))
                else:
                    decoded_parts.append(part.decode('utf-8', errors='replace'))
            else:
                decoded_parts.append(str(part))
        return ''.join(decoded_parts)
    except Exception as e:
        logger.error(f"Error decoding MIME words: {str(e)}")
        return s

def clean_html(html_content):
    """Clean HTML content using BeautifulSoup"""
    if not html_content:
        return ""
    
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Remove script and style elements
        for script_or_style in soup(["script", "style"]):
            script_or_style.extract()
        
        # Remove all attributes except href from links
        for tag in soup.find_all(True):
            if tag.name == 'a' and tag.has_attr('href'):
                href = tag['href']
                tag.attrs = {}
                tag['href'] = href
            else:
                tag.attrs = {}
        
        # Get text
        text = soup.get_text(separator='\n', strip=True)
        
        # Break into lines and remove leading and trailing space on each
        lines = (line.strip() for line in text.splitlines())
        # Break multi-headlines into a line each
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        # Drop blank lines
        text = '\n'.join(chunk for chunk in chunks if chunk)
        
        return text
    except Exception as e:
        logger.error(f"Error cleaning HTML: {str(e)}")
        return "Error cleaning HTML content"

def fetch_emails(limit=100, offset=0):
    """Fetch emails from Gmail using IMAP with deduplication and metrics tracking"""
    if not current_user.gmail_access_token:
        flash("Gmail access token not available. Please re-authenticate.", "warning")
        return {"new": 0, "skipped": 0, "total_time": 0, "emails": []}

    import time
    start_time = time.time()

    try:
        # Connect to Gmail's IMAP server
        mail = imaplib.IMAP4_SSL('imap.gmail.com')
        
        # Authenticate with OAuth2
        auth_string = f'user={current_user.email}\1auth=Bearer {current_user.gmail_access_token}\1\1'
        mail.authenticate('XOAUTH2', lambda x: auth_string)
        
        # Select the mailbox
        mail.select('INBOX')
        
        # Search for all emails
        status, data = mail.search(None, 'ALL')
        if status != 'OK':
            logger.error(f"Error searching for emails: {status}")
            return {"new": 0, "skipped": 0, "total_time": 0, "emails": []}
        
        # Get email IDs
        email_ids = data[0].split()
        
        # Apply pagination
        start_idx = max(0, len(email_ids) - offset - limit)
        end_idx = max(0, len(email_ids) - offset)
        
        # Slice the list to get the required range (in reverse order to get newest first)
        email_ids = email_ids[start_idx:end_idx]
        email_ids.reverse()  # Newest first
        
        emails = []
        new_count = 0
        skipped_count = 0
        
        for e_id in email_ids:
            status, data = mail.fetch(e_id, '(RFC822)')
            if status != 'OK':
                logger.error(f"Error fetching email {e_id}: {status}")
                continue
            
            raw_email = data[0][1]
            email_message = email.message_from_bytes(raw_email)
            
            # Extract email fields
            message_id = email_message.get('Message-ID', '')
            
            # Check if email already exists in database (Deduplication)
            existing_email = Email.query.filter_by(
                user_id=current_user.id,
                message_id=message_id
            ).first()
            
            if existing_email:
                emails.append(existing_email)
                skipped_count += 1
                continue
            
            # Parse email details
            sender_raw = email_message.get('From', '')
            sender_name = None
            sender_email = sender_raw
            
            # Try to extract name and email from the From field
            if '<' in sender_raw and '>' in sender_raw:
                sender_parts = sender_raw.split('<')
                sender_name = decode_mime_words(sender_parts[0].strip(' "\''))
                sender_email = sender_parts[1].strip('>')
            
            # Get recipient
            recipient = email_message.get('To', current_user.email)
            
            # Get subject
            subject = decode_mime_words(email_message.get('Subject', '(No Subject)'))
            
            # Get date
            date_str = email_message.get('Date', '')
            try:
                date_received = email.utils.parsedate_to_datetime(date_str)
            except:
                date_received = datetime.utcnow()
            
            # Get body (both plain text and HTML)
            body_text = None
            body_html = None
            
            if email_message.is_multipart():
                for part in email_message.walk():
                    content_type = part.get_content_type()
                    content_disposition = str(part.get('Content-Disposition'))
                    
                    # Skip attachments
                    if 'attachment' in content_disposition:
                        continue
                    
                    try:
                        payload = part.get_payload(decode=True)
                        if payload:
                            charset = part.get_content_charset() or 'utf-8'
                            payload = payload.decode(charset, errors='replace')
                            
                            if content_type == 'text/plain':
                                body_text = payload
                            elif content_type == 'text/html':
                                body_html = payload
                    except Exception as e:
                        logger.error(f"Error processing email part: {str(e)}")
                        continue
            else:
                # Not multipart - get payload directly
                try:
                    payload = email_message.get_payload(decode=True)
                    if payload:
                        charset = email_message.get_content_charset() or 'utf-8'
                        payload = payload.decode(charset, errors='replace')
                        
                        content_type = email_message.get_content_type()
                        if content_type == 'text/plain':
                            body_text = payload
                        elif content_type == 'text/html':
                            body_html = payload
                except Exception as e:
                    logger.error(f"Error processing email payload: {str(e)}")
            
            # Clean HTML content
            body_cleaned = clean_html(body_html) if body_html else body_text
            
            # Create Email object
            new_email = Email(
                user_id=current_user.id,
                message_id=message_id,
                sender=sender_email,
                sender_name=sender_name,
                recipient=recipient,
                subject=subject,
                body_text=body_text,
                body_html=body_html,
                body_cleaned=body_cleaned,
                date_received=date_received,
                date_processed=datetime.utcnow()
            )
            
            # Add to database
            db.session.add(new_email)
            emails.append(new_email)
            new_count += 1
        
        # Update user progress
        if new_count > 0:
            progress = UserProgress.query.filter_by(user_id=current_user.id).first()
            if progress:
                progress.total_emails_processed += new_count
                progress.last_email_processed = datetime.utcnow()
                progress.last_sync_date = datetime.utcnow()
                
                # Update favorite senders
                senders = {}
                user_emails = Email.query.filter_by(user_id=current_user.id).all()
                for e in user_emails:
                    sender = e.sender
                    senders[sender] = senders.get(sender, 0) + 1
                
                # Get top 5 senders
                top_senders = sorted(senders.items(), key=lambda x: x[1], reverse=True)[:5]
                progress.favorite_senders = json.dumps(dict(top_senders))
                
                db.session.commit()
        
        # Logout from IMAP
        mail.logout()
        total_time = round(time.time() - start_time, 2)
        return {"new": new_count, "skipped": skipped_count, "total_time": total_time, "emails": emails}
    
    except imaplib.IMAP4.error as e:
        logger.exception("IMAP protocol error while fetching emails")
        flash("Failed to fetch emails. Your Gmail access may have expired.", "danger")
        return {"new": 0, "skipped": 0, "total_time": 0, "emails": []}
    except Exception as e:
        logger.exception("An unexpected error occurred while fetching emails")
        flash("An error occurred while fetching emails. Please try again.", "danger")
        return {"new": 0, "skipped": 0, "total_time": 0, "emails": []}


@email_processor_bp.route("/dashboard")
@login_required
def dashboard():
    """Display the user dashboard"""
    # Get user progress
    progress = UserProgress.query.filter_by(user_id=current_user.id).first()
    if not progress:
        progress = UserProgress(user_id=current_user.id)
        db.session.add(progress)
        db.session.commit()
    
    # Get favorite senders
    favorite_senders = {}
    if progress.favorite_senders:
        try:
            favorite_senders = json.loads(progress.favorite_senders)
        except:
            favorite_senders = {}
    
    # Get email stats
    total_emails = Email.query.filter_by(user_id=current_user.id).count()
    read_emails = Email.query.filter_by(user_id=current_user.id, is_read=True).count()
    
    return render_template('dashboard.html', 
                          progress=progress,
                          favorite_senders=favorite_senders,
                          total_emails=total_emails,
                          read_emails=read_emails)

@email_processor_bp.route("/fetch-emails")
@login_required
def fetch_emails_route():
    """Route to fetch emails with deduplication and processing metrics"""
    limit = int(request.args.get('limit', 100))
    offset = int(request.args.get('offset', 0))
    
    # Fetch emails
    stats = fetch_emails(limit, offset)
    db.session.commit()
    
    if isinstance(stats, dict) and 'total_time' in stats:
        flash(f"Sync complete ({stats['total_time']}s): {stats['new']} new emails processed, {stats['skipped']} existing emails skipped.", "success")
    else:
        flash("Emails fetched successfully", "success")
        
    return redirect(url_for('email_processor_bp.emails_list'))

@email_processor_bp.route("/emails")
@login_required
def emails_list():
    """Display and filter the list of emails"""
    from models import PhishingClassification
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    
    query_text = request.args.get('q', '').strip()
    status_filter = request.args.get('status', 'all').strip()
    sender_filter = request.args.get('sender', '').strip()
    
    query = Email.query.filter_by(user_id=current_user.id)
    
    if query_text:
        search_pattern = f"%{query_text}%"
        query = query.filter(
            (Email.subject.ilike(search_pattern)) |
            (Email.body_cleaned.ilike(search_pattern)) |
            (Email.sender.ilike(search_pattern))
        )
        
    if sender_filter:
        query = query.filter(Email.sender.ilike(f"%{sender_filter}%"))
        
    if status_filter in ['phishing', 'legitimate']:
        is_phish = (status_filter == 'phishing')
        query = query.join(PhishingClassification, Email.id == PhishingClassification.email_id).filter(
            PhishingClassification.is_phishing == is_phish
        )
    
    emails_pagination = query.order_by(Email.date_received.desc()).paginate(page=page, per_page=per_page, error_out=False)
    
    return render_template('emails.html', 
                           emails=emails_pagination, 
                           q=query_text, 
                           status=status_filter, 
                           sender=sender_filter)

@email_processor_bp.route("/email/<int:email_id>")
@login_required
def email_detail(email_id):
    """Display a single email"""
    email_obj = Email.query.filter_by(id=email_id, user_id=current_user.id).first_or_404()
    
    # Mark as read if not already
    if not email_obj.is_read:
        email_obj.is_read = True
        
        # Update user progress
        progress = UserProgress.query.filter_by(user_id=current_user.id).first()
        if progress:
            progress.emails_read += 1
            db.session.commit()
    
    return render_template('email_detail.html', email=email_obj)

@email_processor_bp.route("/mark-read/<int:email_id>", methods=['POST'])
@login_required
def mark_read(email_id):
    """Mark an email as read"""
    email_obj = Email.query.filter_by(id=email_id, user_id=current_user.id).first_or_404()
    
    # Mark as read if not already
    if not email_obj.is_read:
        email_obj.is_read = True
        
        # Update user progress
        progress = UserProgress.query.filter_by(user_id=current_user.id).first()
        if progress:
            progress.emails_read += 1
            db.session.commit()
    
    return jsonify({"success": True})
