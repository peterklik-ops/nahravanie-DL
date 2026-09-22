"""
Hlavný orchestrátor - spúšťa celý denný proces:

1. Stiahne nové dodacie listy z Nitech, Eurovat, InterCars
2. Nahrá ich do IC Office (sekcia Sklad)
3. Načíta zákaznícku ponuku z InterCars a upraví predajné ceny v IC Office

Spúšťanie na serveri: naplánujte cez cron, napr. denne o 6:00:
    0 6 * * * cd /cesta/k/agent && /usr/bin/python3 main.py >> /var/log/agent.log 2>&1

Alebo pozri README.md pre alternatívu cez GitHub Actions (scheduled workflow).
"""

from __future__ import annotations

import re
import traceback
from playwright.sync_api import sync_playwright

import config
import notifier
import order_sync
import price_check
from portals import nitech, eurovat, intercars, ic_office
from portals.base import new_context, classify_regular_note, read_csv_codes


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

# Preset mapovania stĺpcov CSV pre vratku/dobropis (záporná hodnota
# dodacieho listu) - iný preset ("NITECH DOBROPIS"/"EUROVAT Dobropis"),
# ale rovnaký dodávateľ (SUPPLIER_NAMES) aj vstupný bod ako pri bežnom
# dodacom liste - potvrdené v praxi cez playwright codegen.
DOBROPIS_COLUMN_SETTINGS = {
    "Nitech": "74",
    "Eurovat": "89",
}

# Poznámka na zápornom dodacom liste, ktorá mení cieľový sklad z "Vratky"
# na "Reklamacie" (uznaná reklamácia dodávateľovi).
UZNANA_REKLAMACIA_NOTE = "uznaná reklamácia"

# Číslo objednávky na začiatku Popisu zákazky (viď
# order_sync.sync_subcustomer_orders() - Popis má tvar "<číslo objednávky>
# <custom_note>"). Staršie ručne vytvorené zákazky môžu mať číslo bez
# predpony "WO" (potvrdené v praxi) - na Nitechu majú objednávky vždy
# tvar "WO<číslo>", preto sa predpona pri hľadaní vždy pridá.
ORDER_NUMBER_IN_DESCRIPTION_PATTERN = re.compile(r"^(?:WO)?(?P<digits>\d+)")


def _disambiguate_zakazka_by_order_items(nitech_page, matches: list[dict], file_path) -> dict:
    """
    Skúsi rozlíšiť medzi viacerými súbežnými zákazkami toho istého
    zákazníka (find_zakazka_for_subcustomer() zlyhalo bez custom_note)
    porovnaním kódov dielov v dodacom liste s kódmi v pôvodnej objednávke
    na Nitechu - číslo objednávky sa vyťaží z Popisu každej kandidátskej
    zákazky (viď ORDER_NUMBER_IN_DESCRIPTION_PATTERN), jej položky sa
    načítajú cez nitech.get_order_item_codes().

    Vráti zákazku, ktorej objednávka obsahuje aspoň jeden kód zhodný s
    dodacím listom - iba ak je taká zákazka PRÁVE JEDNA, inak vyhodí
    ValueError (rovnaká bezpečnostná zásada ako find_zakazka_for_subcustomer).
    """
    file_codes = read_csv_codes(file_path)
    print(f"  [debug] kódy z dodacieho listu: {sorted(file_codes)}")

    resolved = []
    for match in matches:
        description = match["description"]
        order_number_match = ORDER_NUMBER_IN_DESCRIPTION_PATTERN.match(description.strip())
        if not order_number_match:
            print(f"  [debug] Popis {description!r} - nepodarilo sa vyťažiť číslo objednávky")
            continue
        order_number = f"WO{order_number_match.group('digits')}"
        order_codes = nitech.get_order_item_codes(nitech_page, order_number)
        overlap = file_codes & order_codes
        print(
            f"  [debug] {order_number} (Popis {description!r}) -> "
            f"{len(order_codes)} kódov, zhoda: {sorted(overlap)}"
        )
        if overlap:
            resolved.append(match)

    if len(resolved) != 1:
        raise ValueError(
            f"Nepodarilo sa jednoznačne určiť zákazku ani porovnaním kódov "
            f"dielov s objednávkou na Nitechu (zhôd podľa kódov: {len(resolved)} "
            f"spomedzi {len(matches)} kandidátov) - vyžaduje ručnú kontrolu."
        )
    return resolved[0]


def run_delivery_notes_step(browser) -> list[tuple[str, dict]]:
    """
    Stiahne dodacie listy zo všetkých dodávateľských portálov.

    Vráti zoznam dvojíc (názov zdroja, dict) - dict má tvar
    {path, subcustomer_name, custom_note, raw_note}, viď
    portals.*.download_new_delivery_notes().
    """
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


def run_upload_step(browser, files: list[tuple[str, dict]]) -> None:
    """Nahrá stiahnuté dodacie listy do IC Office."""
    if not files:
        print("Žiadne nové dodacie listy na nahratie.")
        return

    context = new_context(browser, config.DOWNLOAD_DIR)
    page = context.new_page()
    # Nitech stránka na dodatočné rozlíšenie medzi viacerými súbežnými
    # zákazkami (viď _disambiguate_zakazka_by_order_items) - vytvorí a
    # prihlási sa iba raz, len ak sa v tomto behu naozaj použije (netreba
    # ju otvárať pri každom behu, len keď nastane nejednoznačnosť).
    nitech_disambig_page = None
    try:
        ic_office.login(page)
        for source_name, item in files:
            file_path = item["path"]
            subcustomer_name = item.get("subcustomer_name")
            custom_note = item.get("custom_note")
            raw_note = item.get("raw_note") or ""
            try:
                if item.get("is_negative_value"):
                    # Vratka/dobropis (záporná hodnota) - potvrdené v praxi
                    # cez playwright codegen: rovnaký vstupný bod aj
                    # dodávateľ ako pri bežnom dodacom liste, mení sa iba
                    # preset stĺpcov (DOBROPIS_COLUMN_SETTINGS), marža sa
                    # vôbec nenastavuje (set_margin=False) a sklad je
                    # "Vratky", alebo "Reklamacie" pri poznámke "uznaná
                    # reklamácia". Táto kontrola musí byť PRVÁ, aby sa taký
                    # dodací list nikdy neomylom nespracoval cez bežnú
                    # (kladnú) cestu nižšie.
                    is_reklamacia = UZNANA_REKLAMACIA_NOTE in raw_note.strip().lower()
                    warehouse_name = "Reklamacie" if is_reklamacia else "Vratky"
                    ic_office.upload_delivery_note(
                        page,
                        file_path,
                        supplier_name=SUPPLIER_NAMES[source_name],
                        column_settings_value=DOBROPIS_COLUMN_SETTINGS[source_name],
                        zakazka_number=None,
                        warehouse_name=warehouse_name,
                        set_margin=False,
                    )
                    print(
                        f"[{source_name}] Nahraný {file_path.name} -> sklad {warehouse_name} "
                        "(vratka/dobropis) - OVERTE RUČNE v Pohyby tovaru / Dodacie listy, "
                        "že diely majú mínusový príznak!"
                    )
                    continue

                if subcustomer_name:
                    try:
                        zakazka = ic_office.find_zakazka_for_subcustomer(
                            page, subcustomer_name, custom_note
                        )
                    except ic_office.AmbiguousZakazkaError as ambiguous:
                        if nitech_disambig_page is None:
                            nitech_disambig_page = context.new_page()
                            nitech.login(nitech_disambig_page)
                        zakazka = _disambiguate_zakazka_by_order_items(
                            nitech_disambig_page, ambiguous.matches, file_path
                        )
                        print(
                            f"[{source_name}] {file_path.name}: rozlíšené medzi "
                            f"{len(ambiguous.matches)} súbežnými zákazkami podľa "
                            "kódov dielov v objednávke"
                        )
                    ic_office.upload_delivery_note(
                        page,
                        file_path,
                        supplier_name=SUPPLIER_NAMES[source_name],
                        column_settings_value=COLUMN_SETTINGS[source_name],
                        zakazka_number=zakazka["number"],
                        subcustomer_name=subcustomer_name,
                    )
                    print(f"[{source_name}] Nahraný {file_path.name} -> zákazka {zakazka['number']}")
                    continue

                classification = classify_regular_note(raw_note)
                route = classification["route"]

                if route == "zakazka":
                    number = classification["zakazka_number"]
                    ic_office.upload_delivery_note(
                        page,
                        file_path,
                        supplier_name=SUPPLIER_NAMES[source_name],
                        column_settings_value=COLUMN_SETTINGS[source_name],
                        zakazka_number=number,
                        margin_percent=ic_office.REGULAR_MARGIN_PERCENT,
                    )
                    print(f"[{source_name}] Nahraný {file_path.name} -> zákazka č. {number}")
                elif route == "sklad":
                    ic_office.upload_delivery_note(
                        page,
                        file_path,
                        supplier_name=SUPPLIER_NAMES[source_name],
                        column_settings_value=COLUMN_SETTINGS[source_name],
                        zakazka_number=None,
                        warehouse_name=ic_office.WAREHOUSE_SKLAD,
                        margin_percent=ic_office.REGULAR_MARGIN_PERCENT,
                    )
                    print(f"[{source_name}] Nahraný {file_path.name} -> priamo na sklad")
                elif route == "servis":
                    ic_office.upload_delivery_note(
                        page,
                        file_path,
                        supplier_name=SUPPLIER_NAMES[source_name],
                        column_settings_value=COLUMN_SETTINGS[source_name],
                        zakazka_number=None,
                        warehouse_name=ic_office.WAREHOUSE_SERVIS,
                        margin_percent=ic_office.REGULAR_MARGIN_PERCENT,
                    )
                    print(f"[{source_name}] Nahraný {file_path.name} -> sklad Servis")
                else:
                    # Vypísať surovú poznámku - ak by parser nesprávne
                    # nevyťažil rozpoznateľný formát tam, kde reálne je,
                    # toto je jediný spôsob, ako to spätne odhaliť.
                    raise NotImplementedError(
                        f"{file_path.name} nemá poznámku podriadeného zákazníka "
                        f"ani rozpoznateľný formát bežnej poznámky "
                        f"(raw_note={raw_note!r}) - vyžaduje ručnú kontrolu."
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
        result = order_sync.sync_subcustomer_orders(nitech_page, ic_page)
        created = result["created"]
        skipped_existing = result["skipped_existing"]

        if created:
            print(f"Vytvorených zákaziek pre podriadených zákazníkov: {len(created)}")
            for order in created:
                print(f"  - {order['order_number']}: {order['subcustomer_name']}")
        if skipped_existing:
            print(f"Preskočené (zákazka už existuje): {len(skipped_existing)}")
            for order in skipped_existing:
                print(f"  - {order['order_number']}: {order['subcustomer_name']}")
        if not created and not skipped_existing:
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
            # Zákazka pre podriadeného zákazníka musí existovať PRED
            # nahrávaním jeho dodacích listov - ak by sa nová objednávka aj
            # jej prvý dodací list objavili v tom istom behu, upload by
            # zákazku nenašiel (potvrdené v praxi - "POTIS s.r.o." malo 0
            # zhôd, lebo run_upload_step bežal pred vytvorením zákazky).
            # Keďže sa dodací list po stiahnutí označí ako spracovaný bez
            # ohľadu na výsledok uploadu, takéto zlyhanie by sa už nikdy
            # samo neopakovalo - preto poradie krokov musí byť opačné.
            run_subcustomer_order_sync_step(browser)
            run_upload_step(browser, files)
            run_price_check_step(browser)
        finally:
            browser.close()


if __name__ == "__main__":
    main()
