"""
Spoločné pomocné funkcie pre všetky portály.

Každý modul portálu (nitech.py, eurovat.py, intercars.py, ic_office.py)
používa rovnaký vzor:

    def login(page): ...
    def download_new_delivery_notes(page, download_dir) -> list[Path]: ...

TIP na doplnenie selektorov:
    Najrýchlejší spôsob ako zistiť presné selektory je spustiť lokálne:

        playwright codegen https://www.nitech.sk/sk/prihlasenie

    Otvorí sa prehliadač + okno, ktoré pri každom vašom kliknutí/vyplnení
    formulára vygeneruje presný riadok kódu (page.fill(...), page.click(...)).
    Tento vygenerovaný kód potom len skopírujete do príslušnej funkcie login().
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from playwright.sync_api import BrowserContext, Page

# Poznámka pri podriadenom zákazníkovi (v Nitechu, na zozname objednávok aj
# na detaile dodacieho listu) má tvar "Podriadený zákazník: MENO (adresa)
# Doprava: ... Platba: ...", prípadne s vlastnou poznámkou zákazníka
# pripojenou za "> " na konci.
SUBCUSTOMER_NAME_PATTERN = re.compile(r"Podriadený zákazník:\s*(?P<name>[^(]+?)\s*\(")
CUSTOM_NOTE_PATTERN = re.compile(r">\s*(?P<custom>.+)", re.DOTALL)

# Poznámka pri bežnom (nie podriadenom) dodacom liste má buď tvar
# "<číslo zákazky> - <priezvisko>" (napr. "7276 - KMEŤ", "7176 Horvathova"
# - pomlčka nie je vždy prítomná), alebo doslovný text "sklad"/"servis"
# (naskladnenie bez priradenia k zákazke) - potvrdené v praxi na reálnych
# poznámkach z bežnej prevádzky.
REGULAR_ZAKAZKA_NUMBER_PATTERN = re.compile(r"^\s*(?P<number>\d+)")


def parse_subcustomer_note(note_text: str) -> dict:
    """
    Rozparsuje poznámku podriadeného zákazníka na meno a prípadnú vlastnú
    poznámku (text za "> "). Ak text nezodpovedá očakávanému tvaru (napr.
    ide o bežnú objednávku bez podriadeného zákazníka), obe polia budú None.
    """
    name_match = SUBCUSTOMER_NAME_PATTERN.search(note_text)
    custom_match = CUSTOM_NOTE_PATTERN.search(note_text)
    return {
        "subcustomer_name": name_match.group("name").strip() if name_match else None,
        "custom_note": custom_match.group("custom").strip() if custom_match else None,
        "raw_note": note_text.strip(),
    }


def classify_regular_note(raw_note: str) -> dict:
    """
    Rozparsuje poznámku BEŽNÉHO dodacieho listu (bez podriadeného
    zákazníka) na spôsob naskladnenia. Vráti {"route", "zakazka_number"}:

    - "zakazka" - poznámka začína číslom zákazky (napr. "7276 - KMEŤ") -
      zakazka_number obsahuje vyťažené číslo.
    - "sklad" - doslovná poznámka "sklad" - naskladniť priamo na sklad
      "Sklad", bez zákazky.
    - "servis" - doslovná poznámka "servis" - naskladniť priamo na sklad
      "Servis", bez zákazky.
    - "unknown" - nerozpoznaný formát, vyžaduje ručnú kontrolu.
    """
    normalized = raw_note.strip().lower()
    if normalized == "sklad":
        return {"route": "sklad", "zakazka_number": None}
    if normalized == "servis":
        return {"route": "servis", "zakazka_number": None}

    number_match = REGULAR_ZAKAZKA_NUMBER_PATTERN.match(raw_note.strip())
    if number_match:
        return {"route": "zakazka", "zakazka_number": number_match.group("number")}

    return {"route": "unknown", "zakazka_number": None}


def read_csv_codes(file_path: Path, column_name: str = "Code", delimiter: str = ";") -> set[str]:
    """
    Načíta hodnoty stĺpca `column_name` (podľa hlavičky) z CSV dodacieho
    listu - podľa reálneho súboru (stĺpce "Code;Mark;Name;Quantity;...",
    oddeľovač ";"). Používa sa na porovnanie kódov dielov s objednávkou
    pri rozlišovaní medzi viacerými súbežnými zákazkami toho istého
    zákazníka (viď ic_office.AmbiguousZakazkaError).
    """
    with file_path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter=delimiter)
        return {row[column_name].strip() for row in reader if row.get(column_name)}


def load_processed_ids(store_path: Path) -> set[str]:
    """Načíta množinu už spracovaných identifikátorov (napr. čísel dokladov) z JSON súboru."""
    if not store_path.exists():
        return set()
    return set(json.loads(store_path.read_text(encoding="utf-8")))


def mark_processed(store_path: Path, id_: str) -> None:
    """Pridá identifikátor do JSON súboru už spracovaných položiek."""
    ids = load_processed_ids(store_path)
    ids.add(id_)
    store_path.parent.mkdir(parents=True, exist_ok=True)
    store_path.write_text(json.dumps(sorted(ids), ensure_ascii=False, indent=2), encoding="utf-8")


def new_context(browser, download_dir: str) -> BrowserContext:
    """Vytvorí nový browser context s povoleným sťahovaním súborov."""
    Path(download_dir).mkdir(parents=True, exist_ok=True)
    context = browser.new_context(accept_downloads=True)
    return context


def wait_and_save_download(page: Page, trigger_locator, download_dir: str) -> Path:
    """
    Klikne na `trigger_locator` (napr. tlačidlo "Stiahnuť") a uloží stiahnutý
    súbor do `download_dir`. Vráti cestu k uloženému súboru.
    """
    with page.expect_download() as download_info:
        trigger_locator.click()
    download = download_info.value
    target_path = Path(download_dir) / download.suggested_filename
    download.save_as(target_path)
    return target_path
