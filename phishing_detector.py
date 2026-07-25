import logging
import json
import re
import os
import numpy as np
import joblib
from datetime import datetime
from flask import Blueprint, jsonify, request, flash, redirect, url_for
from flask_login import login_required, current_user
from app import db
from models import Email, PhishingClassification

# Setup logging
logger = logging.getLogger(__name__)

# Create Blueprint
phishing_detector_bp = Blueprint('phishing_detector_bp', __name__)

# ===============================
# 🔧 Define local file paths
# ===============================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TOKENIZER_PATH = os.path.join(BASE_DIR, "notebooks", "deberta_tokenizer")
MODEL_PATH = os.path.join(BASE_DIR, "notebooks", "deberta_model")
SCALER_PATH = os.path.join(BASE_DIR, "scaler.pkl")
MODEL_DIR = os.path.join(BASE_DIR, "models")

try:
    import torch
    from transformers import AutoTokenizer, AutoModel
    HAS_TORCH = True
except ImportError:
    torch = None
    AutoTokenizer = None
    AutoModel = None
    HAS_TORCH = False
    logger.warning("PyTorch/Transformers not installed. DeBERTa embeddings will be disabled.")

# ===============================
# ✅ Load DeBERTa tokenizer & model
# ===============================
tokenizer = None
deberta_model = None
device = None

if HAS_TORCH:
    try:
        tokenizer = AutoTokenizer.from_pretrained(TOKENIZER_PATH, local_files_only=True)
        deberta_model = AutoModel.from_pretrained(MODEL_PATH, local_files_only=True)
        device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        deberta_model.to(device)
        deberta_model.eval()
        logger.info("✅ DeBERTa tokenizer and model loaded successfully.")
    except Exception as e:
        logger.warning(f"Warning: Could not load DeBERTa model/tokenizer: {e}")

# ===============================
# ✅ Load scaler for LogisticRegression
# ===============================
try:
    scaler = joblib.load(SCALER_PATH)
    logger.info("✅ Scaler loaded successfully.")
except Exception as e:
    logger.warning(f"Warning: Could not load scaler: {e}")
    scaler = None

# ===============================
# ✅ Load all 25 trained models
# ===============================
model_names = ['RandomForest', 'XGBoost', 'LogisticRegression', 'GradientBoosting', 'ExtraTrees']
models = {}

logger.info("Loading 25 trained models...")

for name in model_names:
    for fold in range(1, 6):
        model_path = os.path.join(MODEL_DIR, f"{name}_fold_{fold}.pkl")
        try:
            models[f"{name}_fold_{fold}"] = joblib.load(model_path)
            logger.info(f"✅ Loaded {name}_fold_{fold}")
        except Exception as e:
            logger.warning(f"⚠️ Could not load {name}_fold_{fold}: {e}")

logger.info(f"✅ Total models loaded: {len(models)}")

# ===============================
# 🔍 Helper functions
# ===============================
def get_deberta_embedding(text):
    """Generate DeBERTa CLS embedding for a given text"""
    if not text:
        text = ""
    inputs = tokenizer(
        text,
        return_tensors='pt',
        truncation=True,
        padding=True,
        max_length=512
    )
    inputs = {k: v.to(device) for k, v in inputs.items()}
    with torch.no_grad():
        outputs = deberta_model(**inputs)
    embedding = outputs.last_hidden_state[:, 0, :].cpu().numpy()
    return embedding

def extract_features(email):
    """Extract heuristic-based features for explanations"""
    subject = email.subject or ''
    body = email.body_text or ''
    sender = email.sender or ''

    urgent_keywords = ['urgent', 'immediate', 'alert', 'warning', 'action required',
                       'important', 'asap', 'security notice', 'critical', 'response needed',
                       'final notice', 'attention', 'act now', 'last chance', 'limited time',
                       'your account', 'suspended', 'deactivated', 'failed delivery', 'unusual activity']
    suspicious_info_keywords = ['password', 'verify', 'account', 'click', 'login', 'credentials',
                                'update', 'confirm', 'ssn', 'social security', 'bank', 'security question',
                                'debit card', 'credit card', 'pin number', 'access your account',
                                'you must respond', 'identity', 'personal information', 'reset',
                                're-activate', 'validate', 'unauthorized', 'security alert', 'billing']
    suspicious_links_keywords = ['http', 'https', 'www.', '.php', '.exe', 'bit.ly', 'tinyurl', 'redirect',
                                 'login.', 'secure.', 'update.', 'track.', 'confirm.', 'verify.', 'account.']

    num_urls = len(re.findall(r'http[s]?://[^\s<>"]+|www\.[^\s<>"]+', body))

    features = {
        'has_urgent_subject': int(any(kw in subject.lower() for kw in urgent_keywords)),
        'has_suspicious_links': int(any(kw in body.lower() for kw in suspicious_links_keywords)),
        'has_request_for_info': int(any(kw in body.lower() for kw in suspicious_info_keywords)),
        'sender_domain_match': int(sender.split('@')[-1] in sender.lower() if '@' in sender else False),
        'body_length': len(body),
        'num_urls': num_urls,
        'has_exclamation': int('!' in subject or '!' in body),
        'has_personal_greeting': int(any(kw in body.lower() for kw in ['dear', 'hello', 'hi', 'hey', 'good morning',
                                                                       'good afternoon', 'good evening', 'regards',
                                                                       'sir', 'madam', "ma'dam", 'to whom it may concern', 'ma'])),
        'sender_domain_length': len(sender.split('@')[-1]) if '@' in sender else 0,
        'contains_email_address': int(bool(re.search(r'\b[\w.-]+?@\w+?\.\w+?\b', body))),
        'contains_ip_address': int(bool(re.search(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', body))),
        'has_attachment_reference': int(any(ext in body.lower() for ext in ['.zip', '.pdf', '.doc', '.xls', 'attached', 'attachment', 'file', 'files', 'document']))
    }

    logger.debug(f"Extracted features for email {email.id}: {features}")
    return features

def classify_email(email):
    """Classify an email using DeBERTa embedding + ensemble of loaded models with explainable voting details."""
    import time
    start_time = time.time()
    try:
        full_text = (email.subject or '') + ' ' + (email.body_text or '')
        embedding = get_deberta_embedding(full_text)

        probs = []
        model_votes = {}
        phishing_voters = []
        legit_voters = []

        for name, model in models.items():
            if 'LogisticRegression' in name:
                embedding_scaled = scaler.transform(embedding)
                prob = float(model.predict_proba(embedding_scaled)[0, 1])
            else:
                prob = float(model.predict_proba(embedding)[0, 1])
            
            probs.append(prob)
            is_phish_vote = prob > 0.5
            vote_label = 'phishing' if is_phish_vote else 'legitimate'
            
            model_votes[name] = {
                'probability': round(prob, 4),
                'vote': vote_label
            }
            if is_phish_vote:
                phishing_voters.append(name)
            else:
                legit_voters.append(name)

        if probs:
            phishing_score = float(np.mean(probs))
        else:
            phishing_score = 0.0

        confidence = round(abs(phishing_score - 0.5) * 2 * 100, 1)
        proc_time = round(time.time() - start_time, 4)
        features = extract_features(email)

        research_metadata = {
            'embedding_model': 'DeBERTa-v3-base',
            'phishing_score': round(phishing_score, 4),
            'confidence_percent': confidence,
            'processing_time_sec': proc_time,
            'total_models_evaluated': len(probs),
            'phishing_votes_count': len(phishing_voters),
            'legitimate_votes_count': len(legit_voters),
            'phishing_voters': phishing_voters,
            'legitimate_voters': legit_voters,
            'model_votes': model_votes,
            'heuristic_features': features
        }

        return phishing_score, research_metadata

    except Exception as e:
        logger.error(f"Error classifying email {email.id}: {e}")
        return 0.0, {}

# ===============================
# 🔗 Flask routes
# ===============================
@phishing_detector_bp.route('/analyze_emails')
@login_required
def analyze_emails():
    """Analyze all unclassified emails for phishing with detailed voting telemetry"""
    try:
        emails = Email.query.filter_by(user_id=current_user.id).outerjoin(
            PhishingClassification, Email.id == PhishingClassification.email_id
        ).filter(PhishingClassification.id.is_(None)).all()

        if not emails:
            flash("No new emails to analyze", "info")
            return jsonify({'success': True, 'message': 'No new emails to analyze', 'count': 0})

        analyzed_count = 0
        for email in emails:
            phishing_score, research_meta = classify_email(email)
            classification = PhishingClassification(
                email_id=email.id,
                phishing_score=phishing_score,
                is_phishing=phishing_score > 0.5,
                features_json=json.dumps(research_meta),
                classified_at=datetime.utcnow()
            )
            db.session.add(classification)
            analyzed_count += 1

        db.session.commit()
        flash(f"Successfully analyzed {analyzed_count} emails using 25-fold ML ensemble", "success")
        return jsonify({'success': True, 'message': f'Analyzed {analyzed_count} emails', 'count': analyzed_count})

    except Exception as e:
        logger.error(f"Error analyzing emails: {e}")
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Error analyzing emails', 'error': str(e)}), 500

@phishing_detector_bp.route('/phishing_stats')
@login_required
def phishing_stats():
    """Get statistics for phishing emails"""
    try:
        total_emails = Email.query.filter_by(user_id=current_user.id).count()
        analyzed_emails = PhishingClassification.query.join(
            Email, Email.id == PhishingClassification.email_id
        ).filter(Email.user_id == current_user.id).count()

        phishing_emails = PhishingClassification.query.join(
            Email, Email.id == PhishingClassification.email_id
        ).filter(Email.user_id == current_user.id,
                 PhishingClassification.is_phishing == True).count()

        recent_phishing = PhishingClassification.query.join(
            Email, Email.id == PhishingClassification.email_id
        ).filter(Email.user_id == current_user.id,
                 PhishingClassification.is_phishing == True).order_by(
            PhishingClassification.classified_at.desc()).limit(5).all()

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
            'success': True,
            'total_emails': total_emails,
            'analyzed_emails': analyzed_emails,
            'phishing_emails': phishing_emails,
            'recent_phishing': recent_phishing_data,
            'percentage_phishing': round((phishing_emails / analyzed_emails * 100) if analyzed_emails > 0 else 0, 1)
        })

    except Exception as e:
        logger.error(f"Error getting phishing stats: {str(e)}")
        return jsonify({'success': False, 'error': 'Could not retrieve phishing statistics'}), 500

@phishing_detector_bp.route('/email/<int:email_id>/phishing_details')
@login_required
def phishing_details(email_id):
    """Get phishing details for a specific email"""
    try:
        email = Email.query.filter_by(id=email_id, user_id=current_user.id).first_or_404()
        classification = PhishingClassification.query.filter_by(email_id=email.id).first()

        if not classification:
            phishing_score, features = classify_email(email)
            classification = PhishingClassification(
                email_id=email.id,
                phishing_score=phishing_score,
                is_phishing=phishing_score > 0.5,
                features_json=json.dumps({
                    'embedding_model': 'DeBERTa-v3-base',
                    'phishing_score': phishing_score,
                    'heuristic_features': features
                }),
                classified_at=datetime.utcnow()
            )
            db.session.add(classification)
            db.session.commit()
            flash(f"Email analyzed. Phishing score: {round(phishing_score * 100, 1)}%", "success")

        return jsonify({
            'success': True,
            'email_id': email.id,
            'phishing_score': round(classification.phishing_score * 100, 1),
            'is_phishing': classification.is_phishing,
            'classified_at': classification.classified_at.strftime('%Y-%m-%d %H:%M'),
            'details': json.loads(classification.features_json)
        })

    except Exception as e:
        logger.error(f"Error getting phishing details: {e}")
        return jsonify({'success': False, 'error': 'Could not retrieve phishing details'}), 500

@phishing_detector_bp.route('/email/<int:email_id>/submit_feedback', methods=['POST'])
@login_required
def submit_phishing_feedback(email_id):
    """Submit user feedback on phishing classification"""
    try:
        email = Email.query.filter_by(id=email_id, user_id=current_user.id).first_or_404()
        classification = PhishingClassification.query.filter_by(email_id=email.id).first_or_404()

        is_phishing = request.json.get('is_phishing')
        if is_phishing is not None:
            classification.feedback = bool(is_phishing)
            db.session.commit()
            feedback_type = "phishing" if is_phishing else "legitimate"
            flash(f"Thank you for your feedback. This email has been marked as {feedback_type}.", "success")
            return jsonify({'success': True, 'message': f'Email marked as {feedback_type}'})
        else:
            return jsonify({'success': False, 'error': 'Invalid feedback provided'}), 400

    except Exception as e:
        logger.error(f"Error submitting phishing feedback: {e}")
        return jsonify({'success': False, 'error': 'Could not submit feedback'}), 500
@phishing_detector_bp.route('/email/<int:email_id>/delete_classification', methods=['POST'])
@login_required
def delete_phishing_classification(email_id):
    """Delete phishing classification for an email"""
    try:
        classification = PhishingClassification.query.filter_by(email_id=email_id).first()
        if not classification:
            return jsonify({'success': False, 'error': 'No classification found for this email'}), 404

        db.session.delete(classification)
        db.session.commit()
        flash("Phishing classification deleted successfully.", "success")
        return jsonify({'success': True, 'message': 'Classification deleted successfully'})

    except Exception as e:
        logger.error(f"Error deleting phishing classification: {e}")
        db.session.rollback()
        return jsonify({'success': False, 'error': 'Could not delete classification'}), 500
    
@phishing_detector_bp.route('/email/<int:email_id>/reclassify', methods=['POST'])
@login_required
def reclassify_email(email_id):
    """Reclassify an email and update its phishing score"""
    try:
        email = Email.query.filter_by(id=email_id, user_id=current_user.id).first_or_404()
        phishing_score, features = classify_email(email)

        classification = PhishingClassification.query.filter_by(email_id=email.id).first()
        if not classification:
            classification = PhishingClassification(
                email_id=email.id,
                classified_at=datetime.utcnow()
            )
            db.session.add(classification)

        classification.phishing_score = phishing_score
        classification.is_phishing = phishing_score > 0.5
        classification.features_json = json.dumps({
            'embedding_model': 'DeBERTa-v3-base',
            'phishing_score': phishing_score,
            'heuristic_features': features
        })
        db.session.commit()

        flash(f"Email reclassified. New phishing score: {round(phishing_score * 100, 1)}%", "success")
        return jsonify({'success': True, 'message': 'Email reclassified successfully', 'phishing_score': round(phishing_score * 100, 1)})

    except Exception as e:
        logger.error(f"Error reclassifying email {email_id}: {e}")
        return jsonify({'success': False, 'error': 'Could not reclassify email'}), 500
    
@phishing_detector_bp.route('/email/<int:email_id>/download_features', methods=['GET'])
@login_required
def download_email_features(email_id):
    """Download features of an email as JSON"""
    try:
        email = Email.query.filter_by(id=email_id, user_id=current_user.id).first_or_404()
        classification = PhishingClassification.query.filter_by(email_id=email.id).first()

        if not classification:
            return jsonify({'success': False, 'error': 'No classification found for this email'}), 404

        features = json.loads(classification.features_json)
        response = jsonify(features)
        response.headers['Content-Disposition'] = f'attachment; filename=email_{email_id}_features.json'
        return response

    except Exception as e:
        logger.error(f"Error downloading email features: {e}")
        return jsonify({'success': False, 'error': 'Could not download features'}), 500