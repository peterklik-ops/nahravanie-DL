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

import json
from pathlib import Path
from playwright.sync_api import BrowserContext, Page


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
