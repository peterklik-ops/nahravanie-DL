"""
Modul pre IC Office (webová platforma) - nahratie dodacích listov na sklad
a úprava predajných cien.

STAV: KOSTRA - doplňte selektory podľa reálneho rozhrania IC Office.
"""

from pathlib import Path
from playwright.sync_api import Page

from .. import config


def login(page: Page) -> None:
    page.goto(config.IC_OFFICE_LOGIN_URL)
    # TODO: doplniť selektory prihlasovacieho formulára, napr.:
    # page.fill('#username', config.IC_OFFICE_USERNAME)
    # page.fill('#password', config.IC_OFFICE_PASSWORD)
    # page.click('#login-button')
    # page.wait_for_load_state("networkidle")
    raise NotImplementedError("Doplňte prihlasovacie selektory pre IC Office")


def upload_delivery_note(page: Page, file_path: Path) -> None:
    """
    Prejde do sekcie Sklad a nahrá súbor dodacieho listu.
    """
    # TODO: doplniť navigáciu do sekcie Sklad + nahratie súboru, napr.:
    # page.click('a:has-text("Sklad")')
    # page.click('button:has-text("Nahrať dodací list")')
    # page.set_input_files('input[type="file"]', str(file_path))
    # page.click('button:has-text("Potvrdiť")')
    # page.wait_for_load_state("networkidle")
    raise NotImplementedError("Doplňte logiku nahrávania dodacieho listu do IC Office")


def get_current_sale_price(page: Page, sku: str) -> float:
    """Vráti aktuálnu predajnú cenu produktu v IC Office podľa kódu (SKU)."""
    # TODO: doplniť vyhľadanie produktu a čítanie ceny
    raise NotImplementedError


def update_sale_price(page: Page, sku: str, new_price: float) -> None:
    """Nastaví novú predajnú cenu produktu v IC Office podľa kódu (SKU)."""
    # TODO: doplniť vyhľadanie produktu, úpravu ceny, uloženie
    raise NotImplementedError
