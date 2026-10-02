"""
Jednorazový diagnostický skript - zavolá PRIAMO tú istú funkciu
(ic_office._find_customer_link_by_exact_name), ktorá v produkcii opakovane
zlyháva pri hľadaní zákazníka "Lu-Sy s.r.o.", a vypíše podrobný stav
stránky okolo toho (počet kandidátov, HTML tabuľky, atď.), aby bolo vidieť,
prečo zlyháva aj napriek tomu, že odkaz reálne existuje.

Použitie: python3 debug_lu_sy.py
"""

from __future__ import annotations

from playwright.sync_api import sync_playwright

import config
from portals import ic_office
from portals.base import new_context

CUSTOMER_NAME = "Lu-Sy s.r.o."


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=config.HEADLESS)
        try:
            context = new_context(browser, config.DOWNLOAD_DIR)
            ic_page = context.new_page()
            ic_office.login(ic_page)
            ic_page.get_by_role("link", name=" Klienti ").click()
            print(f"Po kliknuti na Klienti, URL: {ic_page.url}")

            print(f"\nVolam priamo ic_office._find_customer_link_by_exact_name(page, {CUSTOMER_NAME!r})...")
            link = ic_office._find_customer_link_by_exact_name(ic_page, CUSTOMER_NAME)
            print(f"Vysledok: {'NASIEL' if link is not None else 'NENASIEL'}")

            print(f"\nAktualna URL po hladani: {ic_page.url}")

            # Priamy CSS selektor na href vzor, bez has_text filtra - over,
            # ci vobec NEJAKE odkazy na zakaznikov su na stranke pritomne.
            all_customer_links = ic_page.locator('a[href^="/customer/default/"]')
            count = all_customer_links.count()
            print(f"\nPocet VSETKYCH odkazov a[href^='/customer/default/'] na stranke: {count}")
            for i in range(min(count, 10)):
                el = all_customer_links.nth(i)
                print(f"  [{i}] href={el.get_attribute('href')!r} text={el.inner_text()!r}")

            # Skus filter s has_text priamo tu, mimo funkcie.
            filtered = ic_page.locator('a[href^="/customer/default/"]', has_text=CUSTOMER_NAME)
            print(f"\nPocet po has_text filtri ({CUSTOMER_NAME!r}): {filtered.count()}")

            # Vypis cely obsah tabulky (text), nech vidime co tam realne je.
            print("\nCely textovy obsah #database_... alebo hlavnej tabulky (prvych 2000 znakov):")
            body_text = ic_page.locator("body").inner_text()
            idx = body_text.find("Lu-Sy")
            if idx >= 0:
                print(repr(body_text[max(0, idx - 200):idx + 200]))
            else:
                print("'Lu-Sy' sa v CELOM texte stranky (body) vobec nenaslo!")

            context.close()
        finally:
            browser.close()


if __name__ == "__main__":
    main()
