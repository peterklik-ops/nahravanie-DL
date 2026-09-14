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
import order_sync
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

# Názov dodávateľa presne tak, ako sa zobrazuje v IC Office v poli
# "Výber dodávateľa" pri naskladňovaní z dodacieho listu.
SUPPLIER_NAMES = {
    "Nitech": "Autoparts - Nitech",
    "Eurovat": "EURO-VAT",
}

# Uložený preset mapovania stĺpcov CSV (#columnSettings) - líši sa podľa
# dodávateľa, potvrdené ako stály (nemení sa).
COLUMN_SETTINGS = {
    "Nitech": "62",
    "Eurovat": "21",
}


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
                # TODO: automatické párovanie dodacieho listu na správnu
                # zákazku (contract_option_value v IC Office) ešte nie je
                # navrhnuté, preto tento krok zatiaľ nemôže bežať plne
                # automaticky - mechanika naskladnenia je už hotová
                # v ic_office.upload_delivery_note(), len jej chýba táto
                # hodnota. Volanie bude vyzerať takto:
                #
                #   ic_office.upload_delivery_note(
                #       page, file_path,
                #       supplier_name=SUPPLIER_NAMES[source_name],
                #       column_settings_value=COLUMN_SETTINGS[source_name],
                #       contract_option_value=...,  # doplniť
                #       subcustomer_name=...,  # doplniť (kvôli marži)
                #   )
                raise NotImplementedError(
                    f"Chýba automatické určenie zákazky pre {file_path.name} "
                    "(contract_option_value) - upload zatiaľ nemôže bežať bez zásahu."
                )
            except Exception:
                print(f"[CHYBA] Zlyhalo nahratie {file_path.name}:")
                traceback.print_exc()
                notifier.send_alert(
                    f"Agent: zlyhalo nahratie dodacieho listu {file_path.name}",
                    traceback.format_exc(),
                )
    finally:
        context.close()


def run_subcustomer_order_sync_step(browser) -> None:
    """Vytvorí zákazky v IC Office pre nové objednávky podriadených zákazníkov v Nitechu."""
    context = new_context(browser, config.DOWNLOAD_DIR)
    nitech_page = context.new_page()
    ic_page = context.new_page()
    try:
        nitech.login(nitech_page)
        ic_office.login(ic_page)
        created = order_sync.sync_subcustomer_orders(nitech_page, ic_page)
        if created:
            print(f"Vytvorených zákaziek pre podriadených zákazníkov: {len(created)}")
        else:
            print("Žiadne nové objednávky podriadených zákazníkov.")
    except Exception:
        print("[CHYBA] Zlyhala synchronizácia objednávok podriadených zákazníkov:")
        traceback.print_exc()
        notifier.send_alert(
            "Agent: zlyhala synchronizácia objednávok podriadených zákazníkov",
            traceback.format_exc(),
        )
    finally:
        context.close()


def run_price_check_step(browser) -> None:
    """Skontroluje a upraví predajné ceny podľa InterCars ponuky."""
    if not config.INTERCARS_LOGIN_URL:
        # InterCars je zatiaľ vynechaný (Cloudflare ochrana na prihlásení,
        # čaká sa na overenie API/EDI prístupu) - viď main.py PORTALS.
        print("InterCars zatiaľ vynechaný - kontrola cien sa preskakuje.")
        return

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
            run_subcustomer_order_sync_step(browser)
            run_price_check_step(browser)
        finally:
            browser.close()


if __name__ == "__main__":
    main()
