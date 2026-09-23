"""
Odoslanie e-mailového reportu cez Gmail SMTP.

Vyžaduje v .env nastavené SMTP_USERNAME (odosielacia gmail adresa),
SMTP_PASSWORD ("heslo pre aplikácie" - bežné heslo do účtu na SMTP
nefunguje) a ALERT_EMAIL (kam sa majú upozornenia posielať). Bez týchto
troch hodnôt sa report iba vypíše do terminálu, nikam sa neodošle.

send_alert() jednotlivé udalosti počas behu iba zaznamená (vypíše) -
samotný e-mail sa posiela JEDEN raz za celý beh, na konci, cez
send_summary() (volané z main.py) - aby pri viacerých chybách/
upozorneniach v jednom behu neprišlo veľa samostatných e-mailov.
"""

import smtplib
import traceback
from email.mime.text import MIMEText

import config


def send_alert(subject: str, body: str) -> None:
    """Zaznamená upozornenie do priebežného výstupu behu (nezasiela samostatný e-mail)."""
    print(f"[UPOZORNENIE] {subject}\n{body}")


def send_summary(subject: str, body: str) -> None:
    """Odošle JEDEN súhrnný e-mail za celý beh agenta (viď main.py)."""
    if not config.ALERT_EMAIL or not config.SMTP_USERNAME or not config.SMTP_PASSWORD:
        print(f"[SÚHRN - nebol odoslaný, chýba nastavenie e-mailu v .env] {subject}")
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
        print(f"[INFO] Súhrnný e-mail odoslaný na {config.ALERT_EMAIL}: {subject}")
    except Exception:
        # Zlyhanie odoslania e-mailu nesmie zhodiť celý beh agenta - iba
        # sa to vypíše, aby bolo vidieť, že report nedorazil.
        print(f"[CHYBA] Nepodarilo sa odoslať súhrnný e-mail ({subject}):")
        traceback.print_exc()
