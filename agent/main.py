"""
Hlavný orchestrátor - spúšťa celý denný proces:

1. Stiahne nové dodacie listy z Nitech, Eurovat, InterCars
2. Nahrá ich do IC Office (sekcia Sklad)
3. Načíta zákaznícku ponuku z InterCars a upraví predajné ceny v IC Office

Spúšťanie na serveri: naplánujte cez cron, napr. denne o 6:00:
    0 6 * * * cd /cesta/k/agent && /usr/bin/python3 main.py >> /var/log/agent.log 2>&1

Alebo pozri README.md pre alternatívu cez GitHub Actions (scheduled workflow).
"""

import traceback
from playwright.sync_api import sync_playwright

import config
import notifier
import price_check
from portals import nitech, eurovat, intercars, ic_office
from portals.base import new_context


PORTALS = [
    ("Nitech", nitech),
    ("Eurovat", eurovat),
    # InterCars zatiaľ vynechaný - portál má Cloudflare bot ochranu na
    # prihlásení, treba najprv overiť, či existuje oficiálne API/EDI
    # rozhranie pre partnerov, než sa doplní automatizácia cez prehliadač.
    # ("InterCars", intercars),
]


def run_delivery_notes_step(browser) -> list[tuple[str, "Path"]]:
    """Stiahne dodacie listy zo všetkých dodávateľských portálov."""
    all_files = []

    for name, module in PORTALS:
        context = new_context(browser, config.DOWNLOAD_DIR)
        page = context.new_page()
        try:
            module.login(page)
            files = module.download_new_delivery_notes(page, config.DOWNLOAD_DIR)
            print(f"[{name}] Stiahnutých súborov: {len(files)}")
            all_files.extend((name, f) for f in files)
        except Exception:
            print(f"[CHYBA] Zlyhalo sťahovanie z portálu {name}:")
            traceback.print_exc()
            notifier.send_alert(
                f"Agent: zlyhalo sťahovanie z {name}", traceback.format_exc()
            )
        finally:
            context.close()

    return all_files


def run_upload_step(browser, files: list[tuple[str, "Path"]]) -> None:
    """Nahrá stiahnuté dodacie listy do IC Office."""
    if not files:
        print("Žiadne nové dodacie listy na nahratie.")
        return

    context = new_context(browser, config.DOWNLOAD_DIR)
    page = context.new_page()
    try:
        ic_office.login(page)
        for source_name, file_path in files:
            try:
                ic_office.upload_delivery_note(page, file_path)
                print(f"Nahraté do IC Office: {file_path.name} (zdroj: {source_name})")
            except Exception:
                print(f"[CHYBA] Zlyhalo nahratie {file_path.name}:")
                traceback.print_exc()
                notifier.send_alert(
                    f"Agent: zlyhalo nahratie dodacieho listu {file_path.name}",
                    traceback.format_exc(),
                )
    finally:
        context.close()


def run_price_check_step(browser) -> None:
    """Skontroluje a upraví predajné ceny podľa InterCars ponuky."""
    context = new_context(browser, config.DOWNLOAD_DIR)
    ic_page = context.new_page()
    intercars_page = context.new_page()
    try:
        intercars.login(intercars_page)
        offer_prices = intercars.fetch_customer_offer_prices(intercars_page)
        print(f"Načítaných položiek v ponuke: {len(offer_prices)}")

        ic_office.login(ic_page)
        changes = price_check.sync_prices(ic_page, offer_prices)

        if changes:
            summary = "\n".join(
                f"{c['sku']}: {c['old_price']} -> {c['new_price']}" for c in changes
            )
            print(f"Upravené ceny ({len(changes)}):\n{summary}")
            notifier.send_alert(
                f"Agent: upravených {len(changes)} predajných cien", summary
            )
        else:
            print("Žiadne cenové rozdiely nad toleranciu.")
    except Exception:
        print("[CHYBA] Zlyhala kontrola/úprava cien:")
        traceback.print_exc()
        notifier.send_alert("Agent: zlyhala kontrola cien", traceback.format_exc())
    finally:
        context.close()


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=config.HEADLESS)
        try:
            files = run_delivery_notes_step(browser)
            run_upload_step(browser, files)
            run_price_check_step(browser)
        finally:
            browser.close()


if __name__ == "__main__":
    main()
