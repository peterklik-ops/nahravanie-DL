"""
Jednorazový pomocný skript: predoznačí VŠETKY aktuálne zobrazené dodacie
listy v Nitechu aj Eurovate ako "už spracované" (bez sťahovania alebo
nahrávania do IC Office).

Spustite toto PRED prvým ostrým behom main.py, aby download_new_delivery_notes()
nezačal hromadne sťahovať a nahrávať dodacie listy, ktoré už boli ručne
spracované počas vývoja, ale riešil už len naozaj nové dodacie listy od
tejto chvíle.

Použitie (z priečinka agent/, s aktivovaným venv a vyplneným .env):
    python seed_processed_delivery_notes.py
"""

import json
from pathlib import Path
from playwright.sync_api import sync_playwright

import config
from portals import nitech, eurovat
from portals.base import load_processed_ids


def _seed(store_path: Path, numbers: list[str], label: str) -> None:
    combined = load_processed_ids(store_path) | set(numbers)
    store_path.parent.mkdir(parents=True, exist_ok=True)
    store_path.write_text(
        json.dumps(sorted(combined), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[{label}] Nájdených dodacích listov: {len(numbers)}")
    print(f"[{label}] Označených ako už spracované (spolu): {len(combined)}")
    print(f"[{label}] Uložené do: {store_path}")


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=config.HEADLESS)
        try:
            nitech_page = browser.new_page()
            nitech.login(nitech_page)
            nitech_numbers = nitech.list_delivery_note_numbers(nitech_page)

            eurovat_page = browser.new_page()
            eurovat.login(eurovat_page)
            eurovat_numbers = eurovat.list_delivery_note_numbers(eurovat_page)
        finally:
            browser.close()

    _seed(nitech.PROCESSED_DELIVERY_NOTES_FILE, nitech_numbers, "Nitech")
    _seed(eurovat.PROCESSED_DELIVERY_NOTES_FILE, eurovat_numbers, "Eurovat")


if __name__ == "__main__":
    main()
