"""
Jednorazový diagnostický skript - zachytáva, čo presne robí nové
"bezpečnostné overenie" na portáli Nitech (nitech.sk) pri prihlasovaní,
ktoré spôsobilo, že pole "Užívateľské meno / email" prestalo byť
nájditeľné do 30s (potvrdené v praxi, 16.11., opakovane počas celého
dňa). Peter ručne v bežnom prehliadači potvrdil, že sa mu zobrazí okno,
ktoré samo po chvíli zmizne, bez potreby čohokoľvek zadávať/klikať - ide
teda pravdepodobne o JS/anti-bot kontrolu (napr. v štýle Cloudflare),
ktorá môže headless (automatizovaný) prehliadač vyhodnocovať inak než
bežný, viditeľný prehliadač.

Namiesto ďalšieho hádania (napr. len predĺžiť timeout) tento skript:
- otvorí prihlasovaciu stránku presne tak, ako to robí agent (rovnaký
  HEADLESS režim, rovnaký browser context)
- počas 90s postupne (každých ~10s) ukladá screenshoty do
  agent/debug_nitech_screenshots/ a vypisuje, či je pole "Užívateľské
  meno / email" už viditeľné
- zachytáva console správy a JS chyby počas celého čakania
- na konci vypíše, či a za ako dlho sa pole objavilo, aby sa dalo
  rozhodnúť, či stačí predĺžiť čakanie, alebo ide o niečo, čo headless
  prehliadač nikdy neprejde (vyžadovalo by iný prístup)

NEROBÍ žiadne prihlásenie ani zápis - skončí po tejto diagnostike.

Použitie:
    python3 debug_nitech_login.py
"""

from __future__ import annotations

from pathlib import Path

from playwright.sync_api import sync_playwright

import config
from portals.base import new_context

SCREENSHOT_DIR = Path(__file__).parent / "debug_nitech_screenshots"
TOTAL_WAIT_SECONDS = 90
POLL_INTERVAL_SECONDS = 10


def main() -> None:
    SCREENSHOT_DIR.mkdir(exist_ok=True)
    console_messages: list[str] = []
    page_errors: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=config.HEADLESS)
        try:
            context = new_context(browser, config.DOWNLOAD_DIR)
            page = context.new_page()
            page.on("console", lambda msg: console_messages.append(f"[{msg.type}] {msg.text}"))
            page.on("pageerror", lambda exc: page_errors.append(str(exc)))

            print(f"HEADLESS = {config.HEADLESS}")
            print(f"Otváram {config.NITECH_LOGIN_URL} ...")
            page.goto(config.NITECH_LOGIN_URL)

            screenshot_path = SCREENSHOT_DIR / "t00_po_goto.png"
            page.screenshot(path=str(screenshot_path), full_page=True)
            print(f"Screenshot: {screenshot_path.name}")

            username_field = page.get_by_role("textbox", name="Užívaťeľské meno / email")

            elapsed = 0
            field_appeared_at: int | None = None
            while elapsed < TOTAL_WAIT_SECONDS:
                page.wait_for_timeout(POLL_INTERVAL_SECONDS * 1000)
                elapsed += POLL_INTERVAL_SECONDS

                screenshot_path = SCREENSHOT_DIR / f"t{elapsed:02d}_cakanie.png"
                page.screenshot(path=str(screenshot_path), full_page=True)

                visible = username_field.count() > 0 and username_field.is_visible()
                print(f"[t+{elapsed}s] pole viditeľné: {visible}  (screenshot: {screenshot_path.name})")

                if visible and field_appeared_at is None:
                    field_appeared_at = elapsed
                    print(f"\n>>> Pole sa objavilo po {elapsed}s - ďalej už nečakám. <<<\n")
                    break

            print(f"\n--- URL na konci: {page.url} ---")
            print(f"--- Titulok stránky: {page.title()!r} ---")

            print(f"\n--- CONSOLE SPRÁVY ({len(console_messages)}) ---")
            for msg in console_messages[-40:]:
                print(msg)

            print(f"\n--- JS CHYBY ({len(page_errors)}) ---")
            for err in page_errors:
                print(err)

            print("\n--- ZÁVER ---")
            if field_appeared_at is not None:
                print(
                    f"Pole sa objavilo po {field_appeared_at}s. "
                    f"Súčasný timeout vo portals/nitech.py je 30s (predvolený) - "
                    f"{'STAČIL by' if field_appeared_at <= 25 else 'NESTAČIL by'} teda na toto čakanie."
                )
            else:
                print(
                    f"Pole sa neobjavilo ani po {TOTAL_WAIT_SECONDS}s čakania v headless "
                    "režime - pravdepodobne nejde len o pomalé načítanie, ale o niečo, "
                    "čo headless prehliadač vôbec neprejde. Pozri screenshoty v "
                    f"{SCREENSHOT_DIR}/ pre vizuálnu kontrolu."
                )

            context.close()
        finally:
            browser.close()


if __name__ == "__main__":
    main()
