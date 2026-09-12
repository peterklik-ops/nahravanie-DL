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
# Rovnaká platforma ako Nitech (zhodné UI texty aj štruktúra stránky) -
# URL odvodená podľa rovnakého vzoru ako NITECH_DELIVERY_NOTES_URL.
# TODO: overiť, či táto URL naozaj vedie na zoznam dodacích listov.
EUROVAT_DELIVERY_NOTES_URL = os.getenv(
    "EUROVAT_DELIVERY_NOTES_URL", "https://www.eurovat.sk/sk/informacia/dodacie-listy"
)

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

# CSV export skladových zásob z IC Office (Sklady -> Tovar -> export).
# Stĺpce sa dajú premenovať cez *_COLUMN premenné nižšie, ak sa formát
# exportu líši od predpokladaného.
IC_OFFICE_STOCK_CSV = os.getenv("IC_OFFICE_STOCK_CSV", "./downloads/sklad.csv")
IC_OFFICE_STOCK_SKU_COLUMN = os.getenv("IC_OFFICE_STOCK_SKU_COLUMN", "Kód")
IC_OFFICE_STOCK_QUANTITY_COLUMN = os.getenv("IC_OFFICE_STOCK_QUANTITY_COLUMN", "Sklad")
IC_OFFICE_STOCK_NAME_COLUMN = os.getenv("IC_OFFICE_STOCK_NAME_COLUMN", "Názov")
IC_OFFICE_STOCK_CSV_DELIMITER = os.getenv("IC_OFFICE_STOCK_CSV_DELIMITER", ";")
IC_OFFICE_STOCK_CSV_ENCODING = os.getenv("IC_OFFICE_STOCK_CSV_ENCODING", "utf-8-sig")

# --- Allegro (Sale/Offer REST API) ---
# Vytvorte aplikáciu na https://apps.developer.allegro.pl/ (typ "Device
# aplikácia" alebo "Skript") a doplňte client_id/secret. ALLEGRO_REFRESH_TOKEN
# sa získa jednorazovo spustením allegro_device_login.py - viď README.
ALLEGRO_CLIENT_ID = os.getenv("ALLEGRO_CLIENT_ID")
ALLEGRO_CLIENT_SECRET = os.getenv("ALLEGRO_CLIENT_SECRET")
ALLEGRO_REFRESH_TOKEN = os.getenv("ALLEGRO_REFRESH_TOKEN")

# Pre testovanie prepnite na sandbox:
#   ALLEGRO_AUTH_URL=https://allegro.pl.allegrosandbox.pl/auth/oauth
#   ALLEGRO_API_URL=https://api.allegro.pl.allegrosandbox.pl
ALLEGRO_AUTH_URL = os.getenv("ALLEGRO_AUTH_URL", "https://allegro.pl/auth/oauth")
ALLEGRO_API_URL = os.getenv("ALLEGRO_API_URL", "https://api.allegro.pl")

# Súbor, kam sa priebežne ukladá obnovený refresh token (access token
# expiruje po ~12 hodinách, refresh token sa pri obnove typicky mení).
ALLEGRO_TOKEN_STORE = os.getenv("ALLEGRO_TOKEN_STORE", "./allegro_token.json")

# Kam uložiť report chýbajúceho tovaru (v sklade v IC Office, no bez
# zodpovedajúcej ponuky na Allegro podľa kódu/SKU).
ALLEGRO_MISSING_ITEMS_REPORT = os.getenv(
    "ALLEGRO_MISSING_ITEMS_REPORT", "./downloads/allegro_chybajuci_tovar.csv"
)

# --- Všeobecné nastavenia ---
DOWNLOAD_DIR = os.getenv("DOWNLOAD_DIR", "./downloads")
HEADLESS = os.getenv("HEADLESS", "true").lower() == "true"

# Kam poslať upozornenie, ak niečo zlyhá (voliteľné, viď notifier.py)
ALERT_EMAIL = os.getenv("ALERT_EMAIL")
