"""
Jednorazový diagnostický skript - reprodukuje presne ten krok, na ktorom
opakovane zlyháva nahrávanie niektorých dokladov (dl26106776.csv a
podobné): klik na "Naskladniť z dodacieho listu" a následne pole "Výber
dodávateľa", ktoré ostáva "not visible" aj po predĺžení timeoutu na 60s.

Namiesto ďalšieho hádania timeoutov zachytáva:
- JS chyby a console správy počas celého kroku (môže odhaliť zlyhanú AJAX
  requestu alebo JS výnimku, ktorá by vysvetlila, prečo sa modál/snippet
  nevykreslil)
- skutočný stav modálu "#import_export_dl_modal" (trieda, inline štýl)
  a poľa "Výber dodávateľa" v momente, keď by malo byť viditeľné
- screenshot do agent/debug_screenshot.png pre prípadnú vizuálnu kontrolu

NEROBÍ žiadny zápis do skladu - skončí hneď po tejto diagnostike.

Použitie:
    python3 debug_supplier_modal.py
"""

from __future__ import annotations

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

import config
from portals import ic_office
from portals.base import new_context


def main() -> None:
    console_messages: list[str] = []
    page_errors: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=config.HEADLESS)
        try:
            context = new_context(browser, config.DOWNLOAD_DIR)
            page = context.new_page()
            page.on("console", lambda msg: console_messages.append(f"[{msg.type}] {msg.text}"))
            page.on("pageerror", lambda exc: page_errors.append(str(exc)))

            ic_office.login(page)
            page.goto(ic_office.TOVAR_URL)
            print(f"Po goto TOVAR_URL, URL: {page.url}")

            page.get_by_role("link", name="Naskladniť z dodacieho listu").click()
            print("Klikol som na 'Naskladniť z dodacieho listu'.")

            modal = page.locator("#import_export_dl_modal")
            print(f"\n#import_export_dl_modal.count() = {modal.count()}")
            if modal.count() > 0:
                try:
                    cls = modal.get_attribute("class", timeout=2000)
                    style = modal.get_attribute("style", timeout=2000)
                    print(f"class={cls!r}")
                    print(f"style={style!r}")
                    print(f"is_visible()={modal.is_visible()}")
                except Exception as exc:
                    print(f"Chyba pri citani atributov modalu: {exc}")

            supplier_picker = page.locator("#snippet--suppliers").get_by_label("Výber dodávateľa")
            print(f"\nsupplier_picker.count() = {supplier_picker.count()}")
            if supplier_picker.count() > 0:
                try:
                    print(f"supplier_picker.is_visible()={supplier_picker.is_visible()}")
                    html = supplier_picker.first.evaluate("e => e.outerHTML")
                    print(f"outerHTML: {html[:1500]}")
                except Exception as exc:
                    print(f"Chyba pri citani supplier_picker: {exc}")

            print("\n--- Skusam pockat 5s a znova skontrolovat viditelnost ---")
            page.wait_for_timeout(5000)
            if supplier_picker.count() > 0:
                print(f"Po 5s, supplier_picker.is_visible()={supplier_picker.is_visible()}")

            screenshot_path = "debug_screenshot.png"
            page.screenshot(path=screenshot_path, full_page=True)
            print(f"\nScreenshot ulozeny do: {screenshot_path}")

            print(f"\n--- CONSOLE SPRAVY ({len(console_messages)}) ---")
            for msg in console_messages[-40:]:
                print(msg)

            print(f"\n--- JS CHYBY ({len(page_errors)}) ---")
            for err in page_errors:
                print(err)

            try:
                supplier_picker.click(timeout=10000)
                print("\nKlik na supplier_picker NAKONIEC prebehol (po diagnostike).")
            except PlaywrightTimeoutError:
                print("\nKlik na supplier_picker STALE zlyhava aj po diagnostike.")

            context.close()
        finally:
            browser.close()


if __name__ == "__main__":
    main()
