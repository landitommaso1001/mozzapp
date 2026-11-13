import os
import json
import urllib.request
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


def send_email_notification(subject, body_text):
    """
    Sends a silent transactional email directly through your Gmail Apps Script Web App.
    """
    from models import User

    email_row = User.query.filter_by(phone='_email_config').first()
    if not email_row or email_row.price_category != 'ENABLED' or not email_row.name:
        return False, "Notifiche email disabilitate o nessun destinatario configurato."

    webhook_url = os.environ.get("GMAIL_WEBHOOK_URL", "").strip()
    if not webhook_url:
        return False, "Variabile Render GMAIL_WEBHOOK_URL mancante."

    clean_recipients = ",".join([e.strip() for e in email_row.name.split(',') if '@' in e])
    if not clean_recipients:
        return False, "Nessun indirizzo email valido trovato."

    payload = {
        "to": clean_recipients,
        "subject": subject,
        "body": body_text
    }

    req = urllib.request.Request(
        webhook_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            result_text = resp.read().decode("utf-8", errors="ignore")
            if resp.status == 200 and "OK" in result_text:
                return True, "Email inviata con successo tramite Gmail."
            return False, f"Risposta script inattesa: HTTP {resp.status}"
    except Exception as e:
        print(f"⚠️ Gmail Webhook error: {e}")
        return False, str(e)
