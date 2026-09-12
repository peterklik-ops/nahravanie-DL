"""
Centrálna konfigurácia agenta.

DÔLEŽITÉ: Nikdy nevkladajte heslá priamo do kódu.
Všetky prihlasovacie údaje sa načítavajú z premenných prostredia (.env súbor lokálne,
alebo "Secrets" v cloude / CI systéme na serveri).

Vytvorte súbor .env (v .gitignore!) podľa vzoru .env.example
"""

import os
from dotenv import load_dotenv

load_dotenv()

# --- Nitech ---
NITECH_USERNAME = os.getenv("NITECH_USERNAME")
NITECH_PASSWORD = os.getenv("NITECH_PASSWORD")
NITECH_LOGIN_URL = os.getenv("NITECH_LOGIN_URL", "https://www.nitech.sk/sk/prihlasenie")
NITECH_DELIVERY_NOTES_URL = os.getenv(
    "NITECH_DELIVERY_NOTES_URL", "https://www.nitech.sk/sk/informacia/dodacie-listy"
)
NITECH_SUBCUSTOMER_ORDERS_URL = os.getenv(
    "NITECH_SUBCUSTOMER_ORDERS_URL",
    "https://www.nitech.sk/sk/informacia/objednavky-podriadeny-zakaznik",
)

# --- Eurovat ---
EUROVAT_USERNAME = os.getenv("EUROVAT_USERNAME")
EUROVAT_PASSWORD = os.getenv("EUROVAT_PASSWORD")
EUROVAT_LOGIN_URL = os.getenv("EUROVAT_LOGIN_URL", "https://www.eurovat.sk/sk/prihlasenie")
# Poznámka: zoznam dodacích listov sa otvára cez odkaz "Dodacie listy" po
# prihlásení (portals/eurovat.py), nie priamou navigáciou na URL.
EUROVAT_DELIVERY_NOTES_URL = os.getenv("EUROVAT_DELIVERY_NOTES_URL")

# --- InterCars ---
INTERCARS_USERNAME = os.getenv("INTERCARS_USERNAME")
INTERCARS_PASSWORD = os.getenv("INTERCARS_PASSWORD")
INTERCARS_LOGIN_URL = os.getenv("INTERCARS_LOGIN_URL")  # TODO
INTERCARS_DELIVERY_NOTES_URL = os.getenv("INTERCARS_DELIVERY_NOTES_URL")  # TODO
INTERCARS_OFFER_URL = os.getenv("INTERCARS_OFFER_URL")  # TODO: URL zákazníckej ponuky (ceny)

# --- IC Office ---
IC_OFFICE_LOGIN_URL = os.getenv("IC_OFFICE_LOGIN_URL", "https://ic-office.sk/web/login")
IC_OFFICE_USERNAME = os.getenv("IC_OFFICE_USERNAME")
IC_OFFICE_PASSWORD = os.getenv("IC_OFFICE_PASSWORD")

# --- Všeobecné nastavenia ---
DOWNLOAD_DIR = os.getenv("DOWNLOAD_DIR", "./downloads")
HEADLESS = os.getenv("HEADLESS", "true").lower() == "true"

# Kam poslať upozornenie, ak niečo zlyhá (voliteľné, viď notifier.py)
ALERT_EMAIL = os.getenv("ALERT_EMAIL")
