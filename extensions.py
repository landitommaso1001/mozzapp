import os
import json
import urllib.request
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


def send_brevo_notification(subject, body_text):
    """
    Sends a silent transactional email via Brevo HTTPS API (Port 443).
    Reads recipient addresses and ON/OFF state from the '_email_config' User row.
    """
    from models import User

    email_row = User.query.filter_by(phone='_email_config').first()
    if not email_row or email_row.price_category != 'ENABLED' or not email_row.name:
        return False, "Notifiche email disabilitate o nessun destinatario configurato."

    api_key = os.environ.get("BREVO_API_KEY", "").strip()
    sender_email = os.environ.get("BREVO_SENDER_EMAIL", "").strip()
    if not api_key or not sender_email:
        msg = "Variabili Render BREVO_API_KEY o BREVO_SENDER_EMAIL mancanti."
        print(f"⚠️ {msg}")
        return False, msg

    recipients = []
    for raw_email in email_row.name.split(','):
        clean_email = raw_email.strip()
        if '@' in clean_email:
            recipients.append({"email": clean_email})

    if not recipients:
        return False, "Nessun indirizzo email valido trovato."

    payload = {
        "sender": {"name": "MozzApp Caseificio Vicedomini", "email": sender_email},
        "to": recipients,
        "subject": subject,
        "textContent": body_text
    }

    req = urllib.request.Request(
        "https://brevo.com",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "accept": "application/json",
            "api-key": api_key,
            "content-type": "application/json"
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            if resp.status in (200, 201, 202):
                return True, "Email inviata con successo."
            return False, f"Risposta Brevo inattesa: HTTP {resp.status}"
    except Exception as e:
        print(f"⚠️ Brevo email error: {e}")
        return False, str(e)
