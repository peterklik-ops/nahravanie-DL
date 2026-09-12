"""
Jednorazový pomocný skript: predoznačí VŠETKY aktuálne zobrazené objednávky
podriadených zákazníkov v Nitechu ako "už spracované" (bez vytvárania
akýchkoľvek zákaziek v IC Office).

Spustite toto PRED prvým ostrým behom main.py, aby order_sync.py
nezačal hromadne vytvárať zákazky pre celú históriu objednávok, ale
riešil už len naozaj nové objednávky od tejto chvíle.

Použitie (z priečinka agent/, s aktivovaným venv a vyplneným .env):
    python seed_processed_orders.py
"""

import json
from playwright.sync_api import sync_playwright

import config
from portals import nitech
from order_sync import PROCESSED_ORDERS_FILE, _load_processed_order_numbers


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=config.HEADLESS)
        page = browser.new_page()
        try:
            nitech.login(page)
            orders = nitech.list_subcustomer_orders(page)
        finally:
            browser.close()

    existing = _load_processed_order_numbers()
    order_numbers = existing | {o["order_number"] for o in orders}

    PROCESSED_ORDERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    PROCESSED_ORDERS_FILE.write_text(
        json.dumps(sorted(order_numbers), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Nájdených objednávok v Nitechu: {len(orders)}")
    print(f"Označených ako už spracované (spolu): {len(order_numbers)}")
    print(f"Uložené do: {PROCESSED_ORDERS_FILE}")


if __name__ == "__main__":
    main()
