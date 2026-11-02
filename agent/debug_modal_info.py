"""
Jednorazový diagnostický skript - zreprodukuje zmenu stavu zákazky na
"Pracuje sa" (rovnaký krok ako v create_order_for_subcustomer()) na UŽ
EXISTUJÚCEJ zákazke, ktorá je v tomto stave už teraz - teda ide o
bezpečný "no-op" (zopakovanie tej istej hodnoty), žiadne reálne dáta sa
nemenia.

Cieľ: zistiť, prečo po kliknutí "Zmeniť stav" začal od 23.10. blokovať
ĎALŠIE kliknutia dialóg #modalInfo (data-backdrop="static",
data-keyboard="false" - nedá sa zavrieť cez Escape ani klik mimo).
Vypíše jeho obsah a dostupné tlačidlá, aby sa dalo zistiť, ako ho
správne zavrieť.

Použitie: python3 debug_modal_info.py
"""

from __future__ import annotations

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

import config
from portals import ic_office
from portals.base import new_context


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=config.HEADLESS)
        try:
            context = new_context(browser, config.DOWNLOAD_DIR)
            page = context.new_page()
            ic_office.login(page)

            page.get_by_role("link", name=" Zákazky").click()
            page.locator("#state").select_option(ic_office.CONTRACT_STATE_PRACUJE_SA)
            page.wait_for_timeout(2000)

            rows = page.locator("#database_contracts tbody tr")
            print(f"Pocet riadkov v stave 'Pracuje sa': {rows.count()}")
            first_row = rows.first
            custzak = first_row.locator(".custzak")
            number = custzak.locator("span").inner_text().strip()
            print(f"Otvaram prvu zakazku v zozname: {number}")
            custzak.click()

            page.wait_for_timeout(1000)
            print(f"URL po otvoreni zakazky: {page.url}")

            page.get_by_text("Stav", exact=True).click()
            status_frame = page.locator("#stateChange iframe").content_frame
            status_frame.get_by_text("Pracuje sa").click()
            status_frame.get_by_role("button", name="Zmeniť stav").click()
            print("Kliknute na 'Zmenit stav'.")

            page.wait_for_timeout(2000)

            modal_info = page.locator("#modalInfo")
            print(f"\n#modalInfo.count() = {modal_info.count()}")
            if modal_info.count() > 0:
                try:
                    print(f"is_visible() = {modal_info.is_visible()}")
                    html = modal_info.first.evaluate("e => e.outerHTML")
                    print(f"\nouterHTML (max 3000 znakov):\n{html[:3000]}")
                except Exception as exc:
                    print(f"Chyba pri citani #modalInfo: {exc}")

                print("\n--- Vsetky <button> a role=button vo vnutri #modalInfo ---")
                buttons = modal_info.locator("button, [role='button'], a")
                for i in range(buttons.count()):
                    btn = buttons.nth(i)
                    try:
                        text = btn.inner_text(timeout=1000).strip()
                        tag = btn.evaluate("e => e.tagName", timeout=1000)
                        cls = btn.get_attribute("class", timeout=1000)
                        print(f"  [{i}] <{tag}> text={text!r} class={cls!r}")
                    except PlaywrightTimeoutError:
                        print(f"  [{i}] <neviditelny/nedostupny>")

            stateChange = page.locator("#stateChange")
            print(f"\n#stateChange.count() = {stateChange.count()}")
            if stateChange.count() > 0:
                print(f"#stateChange is_visible() = {stateChange.is_visible()}")

            # Skus este raz klik na odkaz "Zakazky" presne ako to robi
            # agent - aby bolo vidiet, ci to teraz naozaj blokuje.
            print("\n--- Skusam klik na odkaz ' Zakazky' (timeout 8s) ---")
            try:
                page.get_by_role("link", name=" Zákazky").click(timeout=8000)
                print("Klik PRESIEL.")
            except PlaywrightTimeoutError:
                print("Klik ZLYHAL (blokovane) - potvrdene.")

            context.close()
        finally:
            browser.close()


if __name__ == "__main__":
    main()
