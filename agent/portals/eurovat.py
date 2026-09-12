"""
Modul pre portál Eurovat - stiahnutie dodacích listov.

STAV: KOSTRA - rovnaký princíp ako nitech.py.
Doplňte config.EUROVAT_LOGIN_URL a config.EUROVAT_DELIVERY_NOTES_URL v .env,
a nižšie selektory podľa reálneho webu.
"""

from pathlib import Path
from playwright.sync_api import Page

from .. import config
from .base import wait_and_save_download


def login(page: Page) -> None:
    page.goto(config.EUROVAT_LOGIN_URL)
    # TODO: doplniť selektory prihlasovacieho formulára
    raise NotImplementedError("Doplňte prihlasovacie selektory pre Eurovat")


def download_new_delivery_notes(page: Page, download_dir: str) -> list[Path]:
    page.goto(config.EUROVAT_DELIVERY_NOTES_URL)
    downloaded_files: list[Path] = []
    # TODO: doplniť logiku zoznamu/sťahovania dodacích listov
    return downloaded_files
