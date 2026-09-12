"""
Modul pre portál Eurovat (eurovat.sk) - stiahnutie dodacích listov.

Rovnaká platforma/UI ako Nitech, selektory doplnené podľa playwright
codegen nahrávky (prihlásenie, výber zákazníckeho profilu, export
dodacieho listu do CSV).
"""

import re
from pathlib import Path
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

import config
from portals.base import wait_and_save_download, load_processed_ids, mark_processed

PROCESSED_DELIVERY_NOTES_FILE = Path(config.DOWNLOAD_DIR).parent / "processed_eurovat_delivery_notes.json"


def login(page: Page) -> None:
    page.goto(config.EUROVAT_LOGIN_URL)

    # Cookie lišta sa pri opakovanom prihlásení (rovnaký browser context)
    # už nemusí zobraziť, preto je klik voliteľný.
    try:
        page.get_by_role("button", name="Potrebné").click(timeout=5000)
    except PlaywrightTimeoutError:
        pass

    page.get_by_role("textbox", name="Užívaťeľské meno / email").fill(config.EUROVAT_USERNAME)
    page.get_by_role("textbox", name="Heslo").fill(config.EUROVAT_PASSWORD)
    page.get_by_role("button", name="Prihlásiť sa").click()

    # Výber zákazníckeho profilu/odberného miesta po prihlásení.
    # #Customer_7765 je stabilné ID tohto účtu (potvrdené), obrazovka sa
    # nemusí zobraziť vždy - preto je klik voliteľný.
    try:
        page.locator("#Customer_7765").click(timeout=5000)
    except PlaywrightTimeoutError:
        pass


def download_new_delivery_notes(page: Page, download_dir: str) -> list[Path]:
    """
    Otvorí sekciu Dodacie listy a stiahne dokumenty, ktoré ešte neboli
    stiahnuté (sledované v PROCESSED_DELIVERY_NOTES_FILE, aby sa pri
    opakovaných behoch nesťahovalo/nenahrávalo to isté).
    """
    page.goto(config.EUROVAT_DELIVERY_NOTES_URL)

    downloaded_files: list[Path] = []
    processed = load_processed_ids(PROCESSED_DELIVERY_NOTES_FILE)

    # Odkazy na jednotlivé dodacie listy sú číslo dokladu, napr. "2662260556".
    # Minimálna dĺžka 6 číslic odlišuje číslo dokladu od prípadných odkazov
    # na stránkovanie (1, 2, 3, ...).
    delivery_note_pattern = re.compile(r"^\d{6,}$")
    count = page.get_by_role("link", name=delivery_note_pattern).count()

    for i in range(count):
        # Po každom stiahnutí sa vraciame na zoznam, preto sa lokátor
        # vyhodnocuje nanovo podľa aktuálneho indexu.
        link = page.get_by_role("link", name=delivery_note_pattern).nth(i)
        document_number = link.inner_text().strip()

        if document_number in processed:
            continue

        link.click()

        export_link = page.get_by_role("link", name="Exportovať do CSV")
        file_path = wait_and_save_download(page, export_link, download_dir)
        downloaded_files.append(file_path)

        mark_processed(PROCESSED_DELIVERY_NOTES_FILE, document_number)
        processed.add(document_number)

        page.goto(config.EUROVAT_DELIVERY_NOTES_URL)

    return downloaded_files
