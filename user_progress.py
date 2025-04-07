import json
from datetime import datetime, timedelta
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from sqlalchemy import func, desc, and_
from app import db
from models import User, Email, UserProgress, PhishingClassification

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
            # Sort by count (most frequent first) and limit to top 10
            favorite_senders = dict(sorted(favorite_senders.items(), 
                                        key=lambda item: item[1], 
                                        reverse=True)[:10])
        except:
            favorite_senders = {}
    
    # Recent activity - get the 10 most recent emails
    recent_emails = Email.query.filter_by(user_id=current_user.id)\
        .order_by(Email.date_processed.desc())\
        .limit(10).all()
    
    # Get time periods for additional stats
    now = datetime.utcnow()
    last_week = now - timedelta(days=7)
    
    # Get emails from the last week
    emails_last_week = Email.query.filter(
        Email.user_id == current_user.id,
        Email.date_received >= last_week
    ).count()
    
    # Get phishing statistics
    phishing_count = PhishingClassification.query.join(
        Email, Email.id == PhishingClassification.email_id
    ).filter(
        Email.user_id == current_user.id,
        PhishingClassification.is_phishing == True
    ).count()
    
    phishing_percentage = (phishing_count / total_emails * 100) if total_emails > 0 else 0
    
    # Get top senders in the last month
    last_month = now - timedelta(days=30)
    top_recent_senders = db.session.query(
        Email.sender,
        func.count(Email.id).label('count')
    ).filter(
        Email.user_id == current_user.id,
        Email.date_received >= last_month
    ).group_by(
        Email.sender
    ).order_by(
        desc('count')
    ).limit(5).all()
    
    # Format top senders for display
    top_senders_dict = {sender: count for sender, count in top_recent_senders}
    
    return render_template('profile.html', 
                          user=current_user,
                          progress=progress,
                          total_emails=total_emails,
                          read_emails=read_emails,
                          read_percentage=read_percentage,
                          favorite_senders=favorite_senders,
                          recent_emails=recent_emails,
                          now=now,
                          emails_last_week=emails_last_week,
                          phishing_count=phishing_count,
                          phishing_percentage=phishing_percentage,
                          top_recent_senders=top_senders_dict)

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

@user_progress_bp.route("/advanced-statistics")
@login_required
def advanced_statistics():
    """Get detailed user statistics for the profile page"""
    try:
        # Get time periods
        now = datetime.utcnow()
        last_week = now - timedelta(days=7)
        last_month = now - timedelta(days=30)
        
        # Basic statistics
        total_emails = Email.query.filter_by(user_id=current_user.id).count()
        read_emails = Email.query.filter_by(user_id=current_user.id, is_read=True).count()
        
        # Time-based statistics
        emails_last_week = Email.query.filter(
            Email.user_id == current_user.id,
            Email.date_received >= last_week
        ).count()
        
        emails_last_month = Email.query.filter(
            Email.user_id == current_user.id,
            Email.date_received >= last_month
        ).count()
        
        # Top senders (last 30 days)
        top_senders = db.session.query(
            Email.sender,
            func.count(Email.id).label('count')
        ).filter(
            Email.user_id == current_user.id,
            Email.date_received >= last_month
        ).group_by(
            Email.sender
        ).order_by(
            desc('count')
        ).limit(5).all()
        
        # Email trends by day of week
        day_of_week_stats = db.session.query(
            func.strftime('%w', Email.date_received).label('day_of_week'),
            func.count(Email.id).label('count')
        ).filter(
            Email.user_id == current_user.id
        ).group_by(
            'day_of_week'
        ).order_by(
            'day_of_week'
        ).all()
        
        # Format day of week data
        days = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
        day_counts = [0] * 7  # Initialize counts for all days
        
        for day_stat in day_of_week_stats:
            if day_stat[0] is not None:  # Check if day is not None
                day_index = int(day_stat[0])
                if 0 <= day_index < 7:  # Validate day index
                    day_counts[day_index] = day_stat[1]
        
        # Get phishing statistics
        phishing_count = PhishingClassification.query.join(
            Email, Email.id == PhishingClassification.email_id
        ).filter(
            Email.user_id == current_user.id,
            PhishingClassification.is_phishing == True
        ).count()
        
        # Reading habits - average time to read emails
        # This is a simplified version - assumes "read" status is set when user reads it
        emails_with_dates = Email.query.filter(
            Email.user_id == current_user.id,
            Email.is_read == True,
            Email.date_received.isnot(None)
        ).limit(50).all()  # Limit to avoid performance issues
        
        # Return data as JSON
        return jsonify({
            'success': True,
            'total_emails': total_emails,
            'read_emails': read_emails,
            'unread_emails': total_emails - read_emails,
            'read_percentage': round((read_emails / total_emails * 100) if total_emails > 0 else 0, 1),
            'emails_last_week': emails_last_week,
            'emails_last_month': emails_last_month,
            'emails_per_day': round(emails_last_month / 30, 1) if emails_last_month > 0 else 0,
            'top_senders': [{'sender': sender, 'count': count} for sender, count in top_senders],
            'day_of_week': {
                'days': days,
                'counts': day_counts
            },
            'phishing': {
                'total': phishing_count,
                'percentage': round((phishing_count / total_emails * 100) if total_emails > 0 else 0, 1)
            }
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

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
