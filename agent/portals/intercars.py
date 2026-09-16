"""
Modul pre portál InterCars - stiahnutie dodacích listov
a načítanie zákazníckej cenovej ponuky (na kontrolu/úpravu predajnej ceny).

STAV: KOSTRA - doplňte selektory podľa reálneho webu InterCars.
"""

from __future__ import annotations

from pathlib import Path
from playwright.sync_api import Page

import config
from portals.base import wait_and_save_download


def login(page: Page) -> None:
    page.goto(config.INTERCARS_LOGIN_URL)
    # TODO: doplniť selektory prihlasovacieho formulára
    raise NotImplementedError("Doplňte prihlasovacie selektory pre InterCars")


def download_new_delivery_notes(page: Page, download_dir: str) -> list[Path]:
    page.goto(config.INTERCARS_DELIVERY_NOTES_URL)
    downloaded_files: list[Path] = []
    # TODO: doplniť logiku zoznamu/sťahovania dodacích listov
    return downloaded_files


def fetch_customer_offer_prices(page: Page) -> dict[str, float]:
    """
    Načíta aktuálnu zákaznícku ponuku (cenník) z InterCars webu pre konkrétneho
    zákazníka a vráti slovník {kód_produktu: cena}.

    Toto je vstup pre price_check.py, ktorý porovná tieto ceny s aktuálnymi
    predajnými cenami v IC Office.
    """
    page.goto(config.INTERCARS_OFFER_URL)

    offer_prices: dict[str, float] = {}

    # TODO: doplniť extrakciu podľa reálnej štruktúry tabuľky ponuky, napr.:
    # rows = page.locator("table.offer-items tbody tr")
    # for i in range(rows.count()):
    #     row = rows.nth(i)
    #     sku = row.locator("td.sku").inner_text().strip()
    #     price_text = row.locator("td.price").inner_text().strip()
    #     price = float(price_text.replace(",", ".").replace("€", "").strip())
    #     offer_prices[sku] = price

    return offer_prices
