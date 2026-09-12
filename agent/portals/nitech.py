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
from portals.base import wait_and_save_download


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


def download_new_delivery_notes(page: Page, download_dir: str) -> list[Path]:
    """
    Otvorí sekciu Dodacie listy a stiahne všetky zobrazené dokumenty cez
    export do CSV.

    TODO: momentálne stiahne VŠETKY dodacie listy zobrazené v zozname pri
    každom spustení - treba doplniť evidenciu už spracovaných čísel
    dokladov (napr. JSON súbor), aby sa duplicitne nesťahovalo/nenahrávalo
    to isté (viď README.md, sekcia "Duplicitné sťahovanie").
    """
    page.goto(config.NITECH_DELIVERY_NOTES_URL)

    downloaded_files: list[Path] = []

    # Odkazy na jednotlivé dodacie listy majú tvar "DL" + číslo dokladu,
    # napr. "DL26092852".
    delivery_note_pattern = re.compile(r"^DL\d+$")
    count = page.get_by_role("link", name=delivery_note_pattern).count()

    for i in range(count):
        # Po každom stiahnutí sa vraciame na zoznam, preto sa lokátor
        # vyhodnocuje nanovo podľa aktuálneho indexu.
        page.get_by_role("link", name=delivery_note_pattern).nth(i).click()

        export_link = page.get_by_role("link", name="Exportovať do CSV")
        file_path = wait_and_save_download(page, export_link, download_dir)
        downloaded_files.append(file_path)

        page.goto(config.NITECH_DELIVERY_NOTES_URL)

    return downloaded_files


# Poznámka v zozname má tvar "Podriadený zákazník: MENO (adresa) Doprava: ... Platba: ...",
# prípadne s vlastnou poznámkou zákazníka pripojenou za "> " na konci.
_SUBCUSTOMER_NAME_PATTERN = re.compile(r"Podriadený zákazník:\s*(?P<name>[^(]+?)\s*\(")
_CUSTOM_NOTE_PATTERN = re.compile(r">\s*(?P<custom>.+)", re.DOTALL)


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

        name_match = _SUBCUSTOMER_NAME_PATTERN.search(note_text)
        custom_match = _CUSTOM_NOTE_PATTERN.search(note_text)

        orders.append({
            "order_number": order_number,
            "subcustomer_name": name_match.group("name").strip() if name_match else None,
            "custom_note": custom_match.group("custom").strip() if custom_match else None,
            "raw_note": note_text.strip(),
        })

    return orders
