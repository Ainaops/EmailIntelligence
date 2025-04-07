import json
from datetime import datetime
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from app import db
from models import User, Email, UserProgress

user_progress_bp = Blueprint('user_progress_bp', __name__)

@user_progress_bp.route("/profile")
@login_required
def profile():
    """Display and manage user profile"""
    # Get user progress
    progress = UserProgress.query.filter_by(user_id=current_user.id).first()
    if not progress:
        progress = UserProgress(user_id=current_user.id)
        db.session.add(progress)
        db.session.commit()
    
    # Calculate statistics
    total_emails = Email.query.filter_by(user_id=current_user.id).count()
    read_emails = Email.query.filter_by(user_id=current_user.id, is_read=True).count()
    read_percentage = (read_emails / total_emails * 100) if total_emails > 0 else 0
    
    # Get favorite senders
    favorite_senders = {}
    if progress.favorite_senders:
        try:
            favorite_senders = json.loads(progress.favorite_senders)
        except:
            favorite_senders = {}
    
    # Recent activity
    recent_emails = Email.query.filter_by(user_id=current_user.id)\
        .order_by(Email.date_processed.desc())\
        .limit(5).all()
    
    return render_template('profile.html', 
                          user=current_user,
                          progress=progress,
                          total_emails=total_emails,
                          read_emails=read_emails,
                          read_percentage=read_percentage,
                          favorite_senders=favorite_senders,
                          recent_emails=recent_emails)

@user_progress_bp.route("/update-username", methods=['POST'])
@login_required
def update_username():
    """Update the user's username"""
    new_username = request.form.get('username')
    
    if not new_username:
        flash("Username cannot be empty", "danger")
        return redirect(url_for('user_progress_bp.profile'))
    
    # Check if username already exists
    existing_user = User.query.filter_by(username=new_username).first()
    if existing_user and existing_user.id != current_user.id:
        flash("Username already taken", "danger")
        return redirect(url_for('user_progress_bp.profile'))
    
    current_user.username = new_username
    db.session.commit()
    
    flash("Username updated successfully", "success")
    return redirect(url_for('user_progress_bp.profile'))

@user_progress_bp.route("/statistics")
@login_required
def statistics():
    """Get user statistics for charts"""
    # Get user progress
    progress = UserProgress.query.filter_by(user_id=current_user.id).first()
    
    # Get emails grouped by date
    from sqlalchemy import func
    email_dates = db.session.query(
        func.date(Email.date_received).label('date'),
        func.count(Email.id).label('count')
    ).filter(Email.user_id == current_user.id)\
     .group_by(func.date(Email.date_received))\
     .order_by(func.date(Email.date_received))\
     .all()
    
    # Format data for charts
    dates = [str(row[0]) for row in email_dates]
    counts = [row[1] for row in email_dates]
    
    # Get favorite senders
    favorite_senders = {}
    if progress and progress.favorite_senders:
        try:
            favorite_senders = json.loads(progress.favorite_senders)
        except:
            favorite_senders = {}
    
    senders = list(favorite_senders.keys())
    sender_counts = list(favorite_senders.values())
    
    # Calculate read vs unread
    total_emails = Email.query.filter_by(user_id=current_user.id).count()
    read_emails = Email.query.filter_by(user_id=current_user.id, is_read=True).count()
    unread_emails = total_emails - read_emails
    
    return jsonify({
        'email_timeline': {
            'dates': dates,
            'counts': counts
        },
        'favorite_senders': {
            'senders': senders,
            'counts': sender_counts
        },
        'read_status': {
            'read': read_emails,
            'unread': unread_emails
        }
    })

@user_progress_bp.route("/reset-progress", methods=['POST'])
@login_required
def reset_progress():
    """Reset user progress and delete emails"""
    try:
        # Delete all emails for the user
        Email.query.filter_by(user_id=current_user.id).delete()
        
        # Reset progress
        progress = UserProgress.query.filter_by(user_id=current_user.id).first()
        if progress:
            progress.total_emails_processed = 0
            progress.emails_read = 0
            progress.last_email_processed = None
            progress.last_sync_date = datetime.utcnow()
            progress.favorite_senders = '{}'
        
        db.session.commit()
        flash("Your progress and emails have been reset", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error resetting progress: {str(e)}", "danger")
    
    return redirect(url_for('user_progress_bp.profile'))
