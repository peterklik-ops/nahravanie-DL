"""
Jednorazový diagnostický skript - porovná presný text mena zákazníka
"Lu-Sy s.r.o." medzi Nitechom (objednávky podriadených zákazníkov) a
IC Office (sekcia Klienti), vrátane neviditeľných znakov (repr()).

Použitie: python3 debug_lu_sy.py
"""

from __future__ import annotations

from playwright.sync_api import sync_playwright

import config
from portals import nitech, ic_office
from portals.base import new_context


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=config.HEADLESS)
        try:
            # --- Nitech: nájsť WO260101045 a vypísať presný subcustomer_name ---
            context = new_context(browser, config.DOWNLOAD_DIR)
            nitech_page = context.new_page()
            nitech.login(nitech_page)
            orders = nitech.list_subcustomer_orders(nitech_page)
            print(f"Nitech: {len(orders)} objednavok celkom")
            for order in orders:
                if order["order_number"] == "WO260101045":
                    print("Najdena objednavka WO260101045:")
                    print(f"  subcustomer_name repr: {order['subcustomer_name']!r}")
                    print(f"  custom_note repr:      {order['custom_note']!r}")
                    print(f"  raw_note repr:         {order['raw_note']!r}")
                    break
            else:
                print("WO260101045 sa v aktualnom zozname nenasla (mozno uz stara).")
            context.close()

            # --- IC Office: hladat "Lu-Sy" (bez exact match) a vypisat vsetky zhody ---
            context = new_context(browser, config.DOWNLOAD_DIR)
            ic_page = context.new_page()
            ic_office.login(ic_page)
            ic_page.get_by_role("link", name=" Klienti ").click()
            search_box = ic_page.get_by_placeholder("Meno / Firma")
            search_box.fill("Lu-Sy")
            search_box.press("Enter")
            ic_page.wait_for_timeout(3000)

            links = ic_page.get_by_role("link").all()
            print("\nIC Office - vsetky odkazy na stranke obsahujuce 'Lu' (po filtri 'Lu-Sy'):")
            found_any = False
            for link in links:
                text = link.inner_text()
                if "lu" in text.lower() or "sy" in text.lower():
                    found_any = True
                    print(f"  repr: {text!r}")
            if not found_any:
                print("  (ziadny odkaz s 'lu'/'sy' v texte sa na stranke nenasiel)")
            context.close()
        finally:
            browser.close()


if __name__ == "__main__":
    main()
