"""
Modul pre portál Nitech (nitech.sk) - stiahnutie dodacích listov.

STAV: KOSTRA - selektory (page.fill/page.click) treba doplniť podľa
skutočného HTML na stránke. Návod je v portals/base.py.

Referencia: https://www.nitech.sk/sk/informacia/dodacie-listy
"""

from pathlib import Path
from playwright.sync_api import Page

from .. import config
from .base import wait_and_save_download


def login(page: Page) -> None:
    page.goto(config.NITECH_LOGIN_URL)

    # TODO: doplniť skutočné selektory prihlasovacieho formulára, napr.:
    # page.fill('input[name="email"]', config.NITECH_USERNAME)
    # page.fill('input[name="password"]', config.NITECH_PASSWORD)
    # page.click('button[type="submit"]')
    # page.wait_for_load_state("networkidle")
    raise NotImplementedError("Doplňte prihlasovacie selektory pre Nitech")


def download_new_delivery_notes(page: Page, download_dir: str) -> list[Path]:
    """
    Otvorí sekciu Dodacie listy a stiahne dokumenty, ktoré ešte neboli
    stiahnuté (odporúčanie: sledovať dátum/číslo posledného spracovaného
    dokladu v malej lokálnej databáze/JSON súbore, aby sa nesťahovalo
    opakovane to isté).
    """
    page.goto(config.NITECH_DELIVERY_NOTES_URL)

    downloaded_files: list[Path] = []

    # TODO: doplniť logiku podľa skutočnej štruktúry zoznamu dodacích listov, napr.:
    # rows = page.locator("table.delivery-notes tbody tr")
    # for i in range(rows.count()):
    #     row = rows.nth(i)
    #     download_button = row.locator("a.download")
    #     file_path = wait_and_save_download(page, download_button, download_dir)
    #     downloaded_files.append(file_path)

    return downloaded_files
