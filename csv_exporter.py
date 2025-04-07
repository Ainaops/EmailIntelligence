import csv
import io
import os
from datetime import datetime
from flask import Blueprint, render_template, redirect, url_for, flash, request, send_file
from flask_login import login_required, current_user
from app import db
from models import Email

csv_exporter_bp = Blueprint('csv_exporter_bp', __name__)

@csv_exporter_bp.route("/export")
@login_required
def export_page():
    """Display the export page"""
    return render_template('export.html')

@csv_exporter_bp.route("/export-csv", methods=['POST'])
@login_required
def export_csv():
    """Export emails to CSV"""
    export_type = request.form.get('export_type', 'all')
    
    # Get emails based on export type
    query = Email.query.filter_by(user_id=current_user.id)
    
    if export_type == 'read':
        query = query.filter_by(is_read=True)
    elif export_type == 'unread':
        query = query.filter_by(is_read=False)
    
    emails = query.order_by(Email.date_received.desc()).all()
    
    if not emails:
        flash("No emails found to export", "warning")
        return redirect(url_for('csv_exporter_bp.export_page'))
    
    # Create CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow([
        'ID', 'Sender', 'Sender Name', 'Recipient', 'Subject',
        'Date Received', 'Date Processed', 'Is Read', 'Message ID',
        'Body (Cleaned)'
    ])
    
    # Write data
    for email in emails:
        writer.writerow([
            email.id,
            email.sender,
            email.sender_name,
            email.recipient,
            email.subject,
            email.date_received.isoformat() if email.date_received else '',
            email.date_processed.isoformat() if email.date_processed else '',
            'Yes' if email.is_read else 'No',
            email.message_id,
            email.body_cleaned[:1000] + '...' if email.body_cleaned and len(email.body_cleaned) > 1000 else email.body_cleaned
        ])
    
    # Prepare file for download
    output.seek(0)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8')),
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'emails_export_{timestamp}.csv'
    )

@csv_exporter_bp.route("/export-sqlite")
@login_required
def export_sqlite():
    """Export SQLite database"""
    # This is a simplified version - in a real app, we'd create a copy of the DB
    # For simplicity, we'll display a message that this would download the DB
    flash("This feature would download a copy of the SQLite database.", "info")
    return redirect(url_for('csv_exporter_bp.export_page'))
