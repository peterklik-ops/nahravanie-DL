"""
Klient pre Allegro REST API (Sale/Offer Management) - autentifikácia cez
OAuth2 Device Flow a základné operácie nad vlastnými ponukami (offers).

STAV: Funkčné je čítanie aktívnych ponúk a úprava skladovej dostupnosti
(`stock.available`) - toto sú stabilné, dlhodobo zdokumentované endpointy
Allegro API. Vytváranie NOVÝCH ponúk (`create_offer`) je zámerne
NEIMPLEMENTOVANÉ - vyžaduje mapovanie produktu na kategóriu Allegro a jej
povinné parametre (líšia sa kategória od kategórie), ktoré nie je možné
uhádnuť. Pozri docstring `create_offer` nižšie.

Autentifikácia: Allegro na úpravu VLASTNÝCH ponúk vyžaduje token viazaný na
konkrétny predajcovský účet (nestačí client_credentials grant, ten je len
na verejné/read-only endpointy). Preto sa používa Device Flow:
  1. Raz spustite `allegro_device_login.py` - vypíše URL a kód, ktorý
     potvrdíte v prehliadači prihlásení ako predajca.
  2. Skript uloží access aj refresh token do `config.ALLEGRO_TOKEN_STORE`.
  3. Tento modul potom refresh token automaticky obnovuje (access token
     platí cca 12 hodín, refresh token sa pri obnove zvyčajne mení -
     preto sa po každom refreshi znova ukladá na disk).
"""

import base64
import csv
import json
import time
from pathlib import Path

import requests

import config

API_HEADERS = {"Accept": "application/vnd.allegro.public.v1+json"}
PATCH_HEADERS = {
    "Accept": "application/vnd.allegro.public.v1+json",
    "Content-Type": "application/vnd.allegro.public.v1+json",
}

_access_token_cache: dict = {"token": None, "expires_at": 0}


def _basic_auth_header() -> dict:
    if not config.ALLEGRO_CLIENT_ID or not config.ALLEGRO_CLIENT_SECRET:
        raise RuntimeError(
            "Chýba ALLEGRO_CLIENT_ID / ALLEGRO_CLIENT_SECRET v .env - "
            "založte aplikáciu na https://apps.developer.allegro.pl/"
        )
    raw = f"{config.ALLEGRO_CLIENT_ID}:{config.ALLEGRO_CLIENT_SECRET}".encode()
    return {"Authorization": f"Basic {base64.b64encode(raw).decode()}"}


def _load_token_store() -> dict:
    path = Path(config.ALLEGRO_TOKEN_STORE)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def _save_token_store(data: dict) -> None:
    path = Path(config.ALLEGRO_TOKEN_STORE)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _current_refresh_token() -> str:
    stored = _load_token_store()
    refresh_token = stored.get("refresh_token") or config.ALLEGRO_REFRESH_TOKEN
    if not refresh_token:
        raise RuntimeError(
            "Chýba Allegro refresh token. Spustite jednorazovo "
            "`python allegro_device_login.py`, prihláste sa ako predajca "
            "a potvrďte prístup aplikácii."
        )
    return refresh_token


def get_access_token() -> str:
    """Vráti platný access token, v prípade potreby ho obnoví cez refresh_token."""
    now = time.time()
    if _access_token_cache["token"] and _access_token_cache["expires_at"] > now + 30:
        return _access_token_cache["token"]

    refresh_token = _current_refresh_token()
    response = requests.post(
        f"{config.ALLEGRO_AUTH_URL}/token",
        headers=_basic_auth_header(),
        data={"grant_type": "refresh_token", "refresh_token": refresh_token},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()

    _access_token_cache["token"] = payload["access_token"]
    _access_token_cache["expires_at"] = now + payload.get("expires_in", 3600)

    # Allegro pri refreshi zvyčajne vydá aj nový refresh_token - uložiť,
    # aby nasledujúci beh (napr. cron o deň neskôr) fungoval ďalej.
    _save_token_store(
        {
            "access_token": payload["access_token"],
            "refresh_token": payload.get("refresh_token", refresh_token),
            "obtained_at": now,
        }
    )
    return _access_token_cache["token"]


def _auth_header() -> dict:
    return {"Authorization": f"Bearer {get_access_token()}"}


def fetch_active_offers() -> dict[str, dict]:
    """
    Načíta všetky aktívne ponuky predajcu a vráti ich ako mapu
    {sku: {"offer_id": ..., "name": ..., "available": ..., "status": ...}}.

    `sku` sa berie z poľa `external.id` ponuky (Allegro pole "ID zo
    systému predajcu" - v ponuke sa nastavuje ako "Kod produktu"/"SKU").
    Ponuky bez vyplneného `external.id` sa preskočia (nedajú sa spárovať
    s IC Office kódom) a vypíše sa upozornenie.
    """
    offers: dict[str, dict] = {}
    offset = 0
    limit = 100

    while True:
        response = requests.get(
            f"{config.ALLEGRO_API_URL}/sale/offers",
            headers={**API_HEADERS, **_auth_header()},
            params={
                "publication.status": "ACTIVE",
                "limit": limit,
                "offset": offset,
            },
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()

        page = payload.get("offers", [])
        for offer in page:
            sku = (offer.get("external") or {}).get("id")
            if not sku:
                print(
                    f"[UPOZORNENIE] Allegro ponuka {offer.get('id')} "
                    f"({offer.get('name')}) nemá vyplnené 'ID zo systému "
                    "predajcu' (external.id) - nedá sa spárovať podľa SKU, preskakujem."
                )
                continue
            offers[sku] = {
                "offer_id": offer["id"],
                "name": offer.get("name"),
                "available": (offer.get("stock") or {}).get("available"),
                "status": (offer.get("publication") or {}).get("status"),
            }

        offset += limit
        if offset >= payload.get("count", payload.get("totalCount", len(page))) or not page:
            break

    return offers


def load_offers_from_csv(csv_path=None) -> dict[str, dict]:
    """
    Načíta export vlastných ponúk z Allegro (predajcovský panel -> Moje
    ponuky -> export do CSV) a vráti ich v rovnakom tvare ako
    `fetch_active_offers` - {sku: {"offer_id", "name", "available",
    "status"}} - podľa stĺpca `config.ALLEGRO_OFFERS_CSV_EXTERNAL_ID_COLUMN`
    (predvolene "EXTERNAL_ID", zodpovedá kódu produktu/SKU v IC Office).

    Toto je alternatíva k `fetch_active_offers` (bez potreby OAuth
    prístupu na čítanie) - na samotnú úpravu skladovej dostupnosti
    (`update_offer_stock`) je OAuth prístup potrebný vždy, keďže sa jedná
    o zápis do konkrétneho predajcovského účtu.

    Ponuky bez vyplneného EXTERNAL_ID sa preskočia (nedajú sa spárovať
    s IC Office kódom).
    """
    path = Path(csv_path or config.ALLEGRO_OFFERS_CSV)
    if not path.exists():
        raise FileNotFoundError(
            f"Súbor s Allegro ponukami '{path}' neexistuje - stiahnite export "
            "z predajcovského panelu (Moje ponuky -> export) a uložte ho na "
            "túto cestu, alebo upravte ALLEGRO_OFFERS_CSV v .env."
        )

    offers: dict[str, dict] = {}
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        sku_column = config.ALLEGRO_OFFERS_CSV_EXTERNAL_ID_COLUMN
        if sku_column not in (reader.fieldnames or []):
            raise ValueError(
                f"CSV '{path}' neobsahuje stĺpec '{sku_column}'. Nájdené "
                f"stĺpce: {reader.fieldnames}."
            )

        for row in reader:
            sku = (row.get(sku_column) or "").strip()
            if not sku:
                print(
                    f"[UPOZORNENIE] Allegro ponuka {row.get('OFFER_ID')} "
                    f"({row.get('NAME')}) nemá vyplnené {sku_column} - "
                    "nedá sa spárovať podľa SKU, preskakujem."
                )
                continue
            try:
                available = int(float(row["STOCK"]))
            except (KeyError, ValueError):
                available = None
            offers[sku] = {
                "offer_id": row.get("OFFER_ID"),
                "name": row.get("NAME"),
                "available": available,
                "status": row.get("STATUS"),
            }

    return offers


def update_offer_stock(offer_id: str, quantity: int) -> None:
    """Nastaví skladovú dostupnosť (počet kusov) danej ponuky."""
    response = requests.patch(
        f"{config.ALLEGRO_API_URL}/sale/offers/{offer_id}",
        headers={**PATCH_HEADERS, **_auth_header()},
        json={"stock": {"available": quantity, "unit": "UNIT"}},
        timeout=30,
    )
    response.raise_for_status()


def end_offer(offer_id: str) -> None:
    """
    Ukončí (stiahne) ponuku - použite pre položky, ktoré už nie sú na
    sklade a nemajú sa ponúkať ako dostupné na 0 ks.

    POZOR: raz ukončenú ponuku Allegro API neumožňuje znova aktivovať -
    ak by mal tovar znova naskladniť, treba vytvoriť novú ponuku (pozri
    `create_offer`). Preto sa toto v `stock_sync.py` používa len voliteľne
    (SYNC_END_OUT_OF_STOCK_OFFERS) a nie automaticky natvrdo.
    """
    response = requests.patch(
        f"{config.ALLEGRO_API_URL}/sale/offers/{offer_id}",
        headers={**PATCH_HEADERS, **_auth_header()},
        json={"publication": {"status": "ENDED"}},
        timeout=30,
    )
    response.raise_for_status()


def create_offer(sku: str, name: str, quantity: int, price: float) -> str:
    """
    NEIMPLEMENTOVANÉ ZÁMERNE. Vytvorenie ponuky na Allegro (POST
    /sale/offers) vyžaduje okrem názvu/ceny/počtu kusov aj:
      - `category.id` - konkrétnu Allegro kategóriu produktu,
      - `parameters` - povinné parametre danej kategórie (líšia sa
        kategória od kategórie, napr. značka, rozmer, OE číslo...),
      - `images`, `description` (formát "sections/items"),
      - `sellingMode` (cena, formát "BUY_NOW"),
      - `delivery.shippingRateId` a `location` podľa cenníka dopravy v účte.

    Tieto údaje sa nedajú odvodiť len z kódu/názvu/množstva v IC Office
    sklade - vyžadujú buď mapovanie IC Office kategórií na Allegro
    kategórie (jednorazovo pripraviť s používateľom), alebo klonovanie
    z podobnej existujúcej ponuky rovnakého typu tovaru.

    Kým toto nie je doplnené, `stock_sync.py` chýbajúci tovar iba
    nahlási (CSV report), nevytvára ponuky automaticky.
    """
    raise NotImplementedError(
        "Vytváranie nových Allegro ponúk vyžaduje mapovanie kategórie a "
        "povinných parametrov - zatiaľ sa chýbajúci tovar iba reportuje."
    )
