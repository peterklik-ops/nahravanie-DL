"""
Odoslanie e-mailového upozornenia cez Gmail SMTP.

Vyžaduje v .env nastavené SMTP_USERNAME (odosielacia gmail adresa),
SMTP_PASSWORD ("heslo pre aplikácie" - bežné heslo do účtu na SMTP
nefunguje) a ALERT_EMAIL (kam sa majú upozornenia posielať). Bez týchto
troch hodnôt sa upozornenie iba vypíše do terminálu, nikam sa neodošle.
"""

import smtplib
import traceback
from email.mime.text import MIMEText

import config


def send_alert(subject: str, body: str) -> None:
    if not config.ALERT_EMAIL or not config.SMTP_USERNAME or not config.SMTP_PASSWORD:
        print(f"[UPOZORNENIE - nebolo odoslané, chýba nastavenie e-mailu v .env] {subject}\n{body}")
        return

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = config.SMTP_USERNAME
    msg["To"] = config.ALERT_EMAIL

    try:
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT) as server:
            server.starttls()
            server.login(config.SMTP_USERNAME, config.SMTP_PASSWORD)
            server.send_message(msg)
        print(f"[INFO] Upozornenie odoslané na {config.ALERT_EMAIL}: {subject}")
    except Exception:
        # Zlyhanie odoslania e-mailu nesmie zhodiť celý beh agenta - iba
        # sa to vypíše, aby bolo vidieť, že upozornenie nedorazilo.
        print(f"[CHYBA] Nepodarilo sa odoslať e-mailové upozornenie ({subject}):")
        traceback.print_exc()
