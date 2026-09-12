"""
Jednoduché odoslanie e-mailového upozornenia (voliteľné).
Použite ľubovoľnú službu, ktorú už máte (SMTP, SendGrid, atď.) -
toto je len minimálny príklad cez SMTP.
"""

import smtplib
from email.mime.text import MIMEText

import config


def send_alert(subject: str, body: str) -> None:
    if not config.ALERT_EMAIL:
        print(f"[UPOZORNENIE - nebolo odoslané, chýba ALERT_EMAIL] {subject}\n{body}")
        return

    # TODO: doplniť skutočné SMTP údaje (alebo nahradiť iným notifikačným
    # kanálom, napr. Slack webhook)
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = config.ALERT_EMAIL
    msg["To"] = config.ALERT_EMAIL

    print(f"[INFO] Upozornenie pripravené na odoslanie: {subject}")
    # with smtplib.SMTP("smtp.example.com", 587) as server:
    #     server.starttls()
    #     server.login(user, password)
    #     server.send_message(msg)
