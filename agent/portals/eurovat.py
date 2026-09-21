"""
Modul pre portál Eurovat (eurovat.sk) - stiahnutie dodacích listov.

Rovnaká platforma/UI ako Nitech, selektory doplnené podľa playwright
codegen nahrávky (prihlásenie, výber zákazníckeho profilu, export
dodacieho listu do CSV).
"""

from __future__ import annotations

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


def list_delivery_note_numbers(page: Page) -> list[str]:
    """
    Vráti čísla dokladov všetkých aktuálne zobrazených dodacích listov,
    bez otvárania detailu alebo sťahovania. Používa sa najmä na seedovanie
    PROCESSED_DELIVERY_NOTES_FILE pred prvým ostrým behom (viď
    seed_processed_delivery_notes.py).
    """
    page.goto(config.EUROVAT_DELIVERY_NOTES_URL)
    delivery_note_pattern = re.compile(r"^\d{6,}$")
    links = page.get_by_role("link", name=delivery_note_pattern)
    return [links.nth(i).inner_text().strip() for i in range(links.count())]


def download_new_delivery_notes(page: Page, download_dir: str) -> list[dict]:
    """
    Otvorí sekciu Dodacie listy a stiahne dokumenty, ktoré ešte neboli
    stiahnuté (sledované v PROCESSED_DELIVERY_NOTES_FILE, aby sa pri
    opakovaných behoch nesťahovalo/nenahrávalo to isté).

    Vráti zoznam slovníkov {path, subcustomer_name, custom_note, raw_note} -
    rovnaký tvar ako nitech.download_new_delivery_notes(). Eurovat beží na
    tej istej platforme ako Nitech, takže sa skúša vyťažiť rovnaká
    "Poznámka" ako pri Nitechu; ak dodací list poznámku podriadeného
    zákazníka nemá (alebo Eurovat túto funkciu vôbec nepoužíva),
    subcustomer_name aj custom_note budú None.
    """
    page.goto(config.EUROVAT_DELIVERY_NOTES_URL)

    downloaded: list[dict] = []
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

        # Záporná hodnota (Cena bez DPH) je viditeľná priamo v zozname
        # (.document-container .table-row.table-content .table-cell,
        # 4. bunka) - vratky/dobropisy sa zatiaľ NEspracovávajú automaticky
        # (dohodnuté, čaká sa na doplnenie), preto treba o zápornej hodnote
        # vedieť ešte pred vyhodnotením poznámky, aby sa takýto dodací list
        # omylom nespracoval cez bežnú (kladnú) cestu.
        price_text = (
            page.locator(".document-container")
            .nth(i)
            .locator(".table-row.table-content .table-cell")
            .nth(3)
            .inner_text()
            .strip()
        )
        is_negative_value = price_text.startswith("-")

        link.click()

        # Po kliknutí sa čaká na skutočné načítanie detailu (môže ísť o
        # AJAX/SPA navigáciu) - okamžitá kontrola .count() by mohla vidieť
        # ešte prázdnu/starú stránku a poznámku podriadeného zákazníka
        # tak nesprávne vyhodnotiť ako chýbajúcu (potvrdené v praxi na
        # rovnakej platforme v nitech.py).
        note_item = page.locator(".footer li", has_text="Poznámka:").first
        try:
            note_item.wait_for(state="visible", timeout=8000)
            raw_note = note_item.locator("span").nth(1).inner_text()
        except PlaywrightTimeoutError:
            raw_note = ""
        note_info = parse_subcustomer_note(raw_note)

        export_link = page.get_by_role("link", name="Exportovať do CSV")
        file_path = wait_and_save_download(page, export_link, download_dir)
        downloaded.append({"path": file_path, "is_negative_value": is_negative_value, **note_info})

        mark_processed(PROCESSED_DELIVERY_NOTES_FILE, document_number)
        processed.add(document_number)

        page.goto(config.EUROVAT_DELIVERY_NOTES_URL)

    return downloaded
