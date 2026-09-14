"""
Modul pre portál Nitech (nitech.sk) - stiahnutie dodacích listov.

Selektory doplnené podľa playwright codegen nahrávky (prihlásenie, výber
zákazníckeho profilu, export dodacieho listu do CSV).

Referencia: https://www.nitech.sk/sk/informacia/dodacie-listy
"""

import re
from pathlib import Path
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

import config
from portals.base import (
    wait_and_save_download,
    load_processed_ids,
    mark_processed,
    parse_subcustomer_note,
)

PROCESSED_DELIVERY_NOTES_FILE = Path(config.DOWNLOAD_DIR).parent / "processed_nitech_delivery_notes.json"


def login(page: Page) -> None:
    page.goto(config.NITECH_LOGIN_URL)

    # Cookie lišta sa pri opakovanom prihlásení (rovnaký browser context)
    # už nemusí zobraziť, preto je klik voliteľný.
    try:
        page.get_by_role("button", name="Potrebné").click(timeout=5000)
    except PlaywrightTimeoutError:
        pass

    page.get_by_role("textbox", name="Užívaťeľské meno / email").fill(config.NITECH_USERNAME)
    page.get_by_role("textbox", name="Heslo").fill(config.NITECH_PASSWORD)
    page.get_by_role("button", name="Prihlásiť sa").click()

    # Výber zákazníckeho profilu/odberného miesta po prihlásení.
    # #Customer_13383 je stabilné ID tohto účtu (potvrdené), obrazovka sa
    # nemusí zobraziť vždy - preto je klik voliteľný.
    try:
        page.locator("#Customer_13383").click(timeout=5000)
    except PlaywrightTimeoutError:
        pass


def download_new_delivery_notes(page: Page, download_dir: str) -> list[dict]:
    """
    Otvorí sekciu Dodacie listy a stiahne dokumenty, ktoré ešte neboli
    stiahnuté (sledované v PROCESSED_DELIVERY_NOTES_FILE, aby sa pri
    opakovaných behoch nesťahovalo/nenahrávalo to isté).

    Vráti zoznam slovníkov {path, subcustomer_name, custom_note, raw_note} -
    detail dodacieho listu obsahuje rovnakú poznámku ako zoznam objednávok
    podriadených zákazníkov ("Podriadený zákazník: MENO (adresa) ... >
    vlastná poznámka"), takže sa dá vyťažiť hneď pri sťahovaní bez ďalšej
    navigácie navyše. Pri bežných (nie podriadený zákazník) dodacích listoch
    budú subcustomer_name aj custom_note None.
    """
    page.goto(config.NITECH_DELIVERY_NOTES_URL)

    downloaded: list[dict] = []
    processed = load_processed_ids(PROCESSED_DELIVERY_NOTES_FILE)

    # Odkazy na jednotlivé dodacie listy majú tvar "DL" + číslo dokladu,
    # napr. "DL26092852".
    delivery_note_pattern = re.compile(r"^DL\d+$")
    count = page.get_by_role("link", name=delivery_note_pattern).count()

    for i in range(count):
        # Po každom stiahnutí sa vraciame na zoznam, preto sa lokátor
        # vyhodnocuje nanovo podľa aktuálneho indexu.
        link = page.get_by_role("link", name=delivery_note_pattern).nth(i)
        document_number = link.inner_text().strip()

        if document_number in processed:
            continue

        link.click()

        note_item = page.locator(".footer li", has_text="Poznámka:")
        raw_note = note_item.locator("span").nth(1).inner_text() if note_item.count() > 0 else ""
        note_info = parse_subcustomer_note(raw_note)

        export_link = page.get_by_role("link", name="Exportovať do CSV")
        file_path = wait_and_save_download(page, export_link, download_dir)
        downloaded.append({"path": file_path, **note_info})

        mark_processed(PROCESSED_DELIVERY_NOTES_FILE, document_number)
        processed.add(document_number)

        page.goto(config.NITECH_DELIVERY_NOTES_URL)

    return downloaded


def list_subcustomer_orders(page: Page) -> list[dict]:
    """
    Vráti zoznam objednávok podriadených zákazníkov (sekcia "objednávky
    podriadených zákazníkov"): číslo objednávky, meno podriadeného
    zákazníka a prípadná vlastná poznámka zákazníka (text za "> ").

    Poznámka: niektoré riadky majú pred textom "Podriadený zákazník:"
    ešte vlastný text bez oddeľovača ">" (napr. "11127823943 piatok
    Podriadený zákazník: ...") - taký text sa zatiaľ nezachytáva,
    custom_note bude v tom prípade None.
    """
    page.goto(config.NITECH_SUBCUSTOMER_ORDERS_URL)

    orders: list[dict] = []
    items = page.locator(".flex-orders-list .document-item")

    for i in range(items.count()):
        item = items.nth(i)
        order_number = item.locator(".document-number a").inner_text().strip()
        note_text = item.locator(".document-note span:not(.grey-foreground)").inner_text()

        orders.append({"order_number": order_number, **parse_subcustomer_note(note_text)})

    return orders
