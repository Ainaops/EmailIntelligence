import logging
import json
from datetime import datetime

from flask import Blueprint, render_template, jsonify, request, flash, redirect, url_for
from flask_login import login_required, current_user
from app import db
from models import Email, PhishingClassification

# Setup logging
logger = logging.getLogger(__name__)

# Create Blueprint
phishing_detector_bp = Blueprint('phishing_detector_bp', __name__)

# Feature extraction functions
def extract_features(email):
    """Extract features from an email for phishing detection
    
    This is a placeholder for the actual feature extraction that would feed into 
    the ensemble machine learning model.
    """
    features = {
        'has_urgent_subject': any(kw in (email.subject or '').lower() for kw in ['urgent', 'immediate', 'alert', 'warning']),
        'has_suspicious_links': 'http' in (email.body_text or '').lower(),
        'has_request_for_info': any(kw in (email.body_text or '').lower() for kw in ['password', 'verify', 'account', 'click']),
        'sender_domain_match': email.sender.split('@')[-1] in email.sender_name.lower() if email.sender_name else False,
        'body_length': len(email.body_text or ''),
        'date_received': email.date_received.timestamp() if email.date_received else 0,
    }
    return features

def classify_email(email_features):
    """Apply ensemble model to classify an email as phishing or legitimate
    
    Currently a placeholder that will later be replaced with actual ML model inference.
    This function simulates a model scoring emails on phishing probability.
    """
    # Placeholder for actual model scoring
    # In a real implementation, this would call a properly trained ML model
    
    # Basic heuristic scoring (to be replaced by actual ML model)
    score = 0.0
    
    if email_features['has_urgent_subject']:
        score += 0.3
    if email_features['has_suspicious_links']:
        score += 0.3
    if email_features['has_request_for_info']:
        score += 0.3
    if not email_features['sender_domain_match']:
        score += 0.2
    
    # Cap at 0.95 for placeholder model
    return min(score, 0.95)

@phishing_detector_bp.route('/phishing_detection')
@login_required
def phishing_detection_dashboard():
    """Display the phishing detection dashboard"""
    return render_template('phishing_detection.html')

@phishing_detector_bp.route('/analyze_emails')
@login_required
def analyze_emails():
    """Analyze all unclassified emails for phishing"""
    try:
        # Get all unclassified emails
        emails = Email.query.filter_by(
            user_id=current_user.id
        ).outerjoin(
            PhishingClassification, 
            Email.id == PhishingClassification.email_id
        ).filter(
            PhishingClassification.id.is_(None)
        ).all()
        
        if not emails:
            flash("No new emails to analyze", "info")
            return redirect(url_for('phishing_detector_bp.phishing_detection_dashboard'))
        
        analyzed_count = 0
        for email in emails:
            # Extract features
            features = extract_features(email)
            
            # Classify using model
            phishing_score = classify_email(features)
            
            # Save classification
            classification = PhishingClassification(
                email_id=email.id,
                phishing_score=phishing_score,
                is_phishing=phishing_score > 0.5,  # Threshold can be adjusted
                features_json=json.dumps(features),
                classified_at=datetime.utcnow()
            )
            db.session.add(classification)
            analyzed_count += 1
        
        db.session.commit()
        flash(f"Successfully analyzed {analyzed_count} emails", "success")
        
    except Exception as e:
        logger.error(f"Error analyzing emails: {str(e)}")
        flash("Error analyzing emails", "danger")
        db.session.rollback()
    
    return redirect(url_for('phishing_detector_bp.phishing_detection_dashboard'))

@phishing_detector_bp.route('/phishing_stats')
@login_required
def phishing_stats():
    """Get statistics for phishing emails"""
    try:
        # Get counts
        total_emails = Email.query.filter_by(user_id=current_user.id).count()
        analyzed_emails = PhishingClassification.query.join(
            Email, Email.id == PhishingClassification.email_id
        ).filter(
            Email.user_id == current_user.id
        ).count()
        
        phishing_emails = PhishingClassification.query.join(
            Email, Email.id == PhishingClassification.email_id
        ).filter(
            Email.user_id == current_user.id,
            PhishingClassification.is_phishing == True
        ).count()
        
        # Get latest phishing emails
        recent_phishing = PhishingClassification.query.join(
            Email, Email.id == PhishingClassification.email_id
        ).filter(
            Email.user_id == current_user.id,
            PhishingClassification.is_phishing == True
        ).order_by(
            PhishingClassification.classified_at.desc()
        ).limit(5).all()
        
        recent_phishing_data = []
        for classification in recent_phishing:
            email = Email.query.get(classification.email_id)
            if email:
                recent_phishing_data.append({
                    'id': email.id,
                    'sender': email.sender,
                    'subject': email.subject,
                    'date': email.date_received.strftime('%Y-%m-%d %H:%M') if email.date_received else 'Unknown',
                    'phishing_score': round(classification.phishing_score * 100, 1)
                })
        
        return jsonify({
            'total_emails': total_emails,
            'analyzed_emails': analyzed_emails,
            'phishing_emails': phishing_emails,
            'recent_phishing': recent_phishing_data,
            'percentage_phishing': round((phishing_emails / analyzed_emails * 100) if analyzed_emails > 0 else 0, 1)
        })
        
    except Exception as e:
        logger.error(f"Error getting phishing stats: {str(e)}")
        return jsonify({'error': 'Could not retrieve phishing statistics'}), 500

@phishing_detector_bp.route('/email/<int:email_id>/phishing_details')
@login_required
def phishing_details(email_id):
    """Get phishing details for a specific email"""
    try:
        email = Email.query.filter_by(id=email_id, user_id=current_user.id).first_or_404()
        
        classification = PhishingClassification.query.filter_by(email_id=email.id).first()
        
        if not classification:
            # If not classified yet, do it now
            features = extract_features(email)
            phishing_score = classify_email(features)
            
            classification = PhishingClassification(
                email_id=email.id,
                phishing_score=phishing_score,
                is_phishing=phishing_score > 0.5,
                features_json=json.dumps(features),
                classified_at=datetime.utcnow()
            )
            db.session.add(classification)
            db.session.commit()
        
        # Parse features
        features = json.loads(classification.features_json)
        
        # Get explanations for phishing indicators
        explanations = []
        if features.get('has_urgent_subject'):
            explanations.append("Contains urgent or alarming language in the subject")
        if features.get('has_suspicious_links'):
            explanations.append("Contains links that might lead to malicious websites")
        if features.get('has_request_for_info'):
            explanations.append("Asks for sensitive information like passwords or account details")
        if not features.get('sender_domain_match'):
            explanations.append("Sender email domain doesn't match the sender's claimed identity")
        
        return jsonify({
            'email_id': email.id,
            'phishing_score': round(classification.phishing_score * 100, 1),
            'is_phishing': classification.is_phishing,
            'classified_at': classification.classified_at.strftime('%Y-%m-%d %H:%M'),
            'explanations': explanations,
            'user_feedback': classification.feedback
        })
        
    except Exception as e:
        logger.error(f"Error getting phishing details: {str(e)}")
        return jsonify({'error': 'Could not retrieve phishing details'}), 500

@phishing_detector_bp.route('/email/<int:email_id>/submit_feedback', methods=['POST'])
@login_required
def submit_phishing_feedback(email_id):
    """Submit user feedback on phishing classification"""
    try:
        email = Email.query.filter_by(id=email_id, user_id=current_user.id).first_or_404()
        classification = PhishingClassification.query.filter_by(email_id=email.id).first_or_404()
        
        # Get feedback from form data (True=phishing, False=not phishing)
        is_phishing = request.json.get('is_phishing')
        
        if is_phishing is not None:
            # Update the classification with user feedback
            classification.feedback = bool(is_phishing)
            db.session.commit()
            
            feedback_type = "phishing" if is_phishing else "legitimate"
            flash(f"Thank you for your feedback. This email has been marked as {feedback_type}.", "success")
            return jsonify({'success': True, 'message': f'Email marked as {feedback_type}'})
        else:
            return jsonify({'error': 'Invalid feedback provided'}), 400
            
    except Exception as e:
        logger.error(f"Error submitting phishing feedback: {str(e)}")
        return jsonify({'error': 'Could not submit feedback'}), 500