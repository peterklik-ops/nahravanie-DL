"""
Porovná skladové zásoby z IC Office (XLSX/CSV export) so zoznamom ponúk na
Allegro (CSV export z predajcovského panelu, alebo živé REST API) a:
  1. upraví skladovú dostupnosť (počet kusov) na Allegro pri položkách,
     ktoré sa spárujú podľa kódu/SKU (presne, alebo približne - pozri
     `normalize_sku`) a majú iný počet kusov,
  2. voliteľne ukončí Allegro ponuky, ktoré sú v IC Office na 0 ks
     (SYNC_END_OUT_OF_STOCK_OFFERS - vypnuté predvolene, pozri POZOR
     v `allegro.end_offer`),
  3. tovar, ktorý JE na sklade v IC Office, ale NEMÁ zodpovedajúcu
     Allegro ponuku podľa kódu/SKU, zapíše do CSV reportu zoradeného
     podľa predajnej ceny zostupne (config.ALLEGRO_MISSING_ITEMS_REPORT)
     - najdrahšie položky prvé, keďže sa nahrávajú na Allegro manuálne
     a s prioritou. Automatické vytvorenie ponuky nie je implementované,
     pozri `allegro.create_offer`.

Párovanie podľa SKU: Allegro EXTERNAL_ID má niekedy dopísanú poznámku za
medzerou (napr. "1800402 bazos" namiesto IC Office kódu "1800402") -
`normalize_sku` porovnáva aj podľa prvého "slova" pred medzerou, takže sa
tieto ponuky tiež považujú za spárované (potvrdené na reálnom exporte -
množstvá sedeli až na jednu výnimku).

Vstup: export skladu z IC Office (config.IC_OFFICE_STOCK_FILE, .xlsx alebo
.csv) a export ponúk z Allegro (config.ALLEGRO_OFFERS_CSV).
"""

import csv
from pathlib import Path

import allegro
import config

# Ak True, Allegro ponuky pre tovar na 0 ks v IC Office sa rovno ukončia.
# Pozor: ukončenú ponuku Allegro API neumožňuje znova aktivovať - preto je
# toto predvolene vypnuté, kým sa nepotvrdí, že je to naozaj žiaduce.
SYNC_END_OUT_OF_STOCK_OFFERS = False


def load_ic_office_stock(path: str | Path = None) -> dict[str, dict]:
    """
    Načíta export skladu z IC Office (.xlsx alebo .csv, podľa prípony) a
    vráti mapu {sku: {"quantity": int, "name": str}}.
    """
    file_path = Path(path or config.IC_OFFICE_STOCK_FILE)
    if not file_path.exists():
        raise FileNotFoundError(
            f"Súbor so skladom '{file_path}' neexistuje - stiahnite export z "
            "IC Office (Sklady -> Tovar -> export) a uložte ho na túto "
            "cestu, alebo upravte IC_OFFICE_STOCK_FILE v .env."
        )

    if file_path.suffix.lower() == ".xlsx":
        rows = _read_xlsx_rows(file_path)
    else:
        rows = _read_csv_rows(file_path)

    return _rows_to_stock(rows, str(file_path))


def _read_xlsx_rows(path: Path) -> list[dict]:
    import openpyxl

    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    ws = wb.active
    rows_iter = ws.iter_rows(values_only=True)
    header = [str(h).strip() if h is not None else "" for h in next(rows_iter)]
    return [dict(zip(header, row)) for row in rows_iter]


def _read_csv_rows(path: Path) -> list[dict]:
    with path.open(encoding=config.IC_OFFICE_STOCK_CSV_ENCODING, newline="") as f:
        reader = csv.DictReader(f, delimiter=config.IC_OFFICE_STOCK_CSV_DELIMITER)
        return list(reader)


def _rows_to_stock(rows: list[dict], source_label: str) -> dict[str, dict]:
    if not rows:
        return {}

    missing_columns = {
        config.IC_OFFICE_STOCK_SKU_COLUMN,
        config.IC_OFFICE_STOCK_QUANTITY_COLUMN,
    } - set(rows[0].keys())
    if missing_columns:
        raise ValueError(
            f"'{source_label}' neobsahuje očakávané stĺpce {missing_columns}. "
            f"Nájdené stĺpce: {list(rows[0].keys())}. Upravte "
            "IC_OFFICE_STOCK_SKU_COLUMN / IC_OFFICE_STOCK_QUANTITY_COLUMN "
            "v .env podľa skutočného exportu."
        )

    stock: dict[str, dict] = {}
    for row in rows:
        sku = str(row.get(config.IC_OFFICE_STOCK_SKU_COLUMN) or "").strip()
        if not sku:
            continue

        quantity_raw = row.get(config.IC_OFFICE_STOCK_QUANTITY_COLUMN)
        if quantity_raw is None or str(quantity_raw).strip() == "":
            continue
        try:
            quantity = int(float(str(quantity_raw).strip().replace(",", ".")))
        except ValueError:
            print(f"[UPOZORNENIE] Neplatné množstvo '{quantity_raw}' pre SKU {sku}, preskakujem.")
            continue

        name = str(row.get(config.IC_OFFICE_STOCK_NAME_COLUMN) or "").strip()

        price_raw = row.get(config.IC_OFFICE_STOCK_PRICE_COLUMN)
        try:
            price = float(str(price_raw).strip().replace(",", ".")) if price_raw not in (None, "") else 0.0
        except ValueError:
            price = 0.0

        stock[sku] = {"quantity": quantity, "name": name, "price": price}

    return stock


def normalize_sku(raw: str) -> str:
    """
    Vráti prvé "slovo" pred medzerou. Allegro EXTERNAL_ID má niekedy
    dopísanú poznámku za medzerou (napr. "1800402 bazos" -> "1800402"),
    ktorá sa v IC Office kóde nenachádza.
    """
    raw = raw.strip()
    return raw.split()[0] if raw else raw


def compute_diff(ic_office_stock: dict[str, dict], allegro_offers: dict[str, dict]) -> dict:
    """
    Čisto porovnávacia logika (bez sieťových volaní). Vráti:
      - "updates": zoznam spárovaných ponúk (presne, alebo približne cez
        `normalize_sku` - napr. Allegro "1800402 bazos" ~ IC Office
        "1800402") s iným počtom kusov
      - "unchanged": počet spárovaných ponúk s rovnakým počtom kusov
      - "missing_in_allegro": tovar v IC Office (>0 ks) bez zodpovedajúcej
        Allegro ponuky (ani presnej, ani približnej zhody), zoradený podľa
        ceny zostupne (najdrahšie prvé)
    """
    updates = []
    unchanged = 0
    matched_ic_skus = set()

    normalized_ic_index: dict[str, str] = {}
    for ic_sku in ic_office_stock:
        normalized_ic_index.setdefault(normalize_sku(ic_sku), ic_sku)

    for sku, offer in allegro_offers.items():
        ic_sku = sku if sku in ic_office_stock else normalized_ic_index.get(normalize_sku(sku))
        if not ic_sku:
            continue

        matched_ic_skus.add(ic_sku)
        ic_quantity = ic_office_stock[ic_sku]["quantity"]
        if offer["available"] == ic_quantity:
            unchanged += 1
        else:
            updates.append(
                {
                    "sku": sku,
                    "ic_office_kod": ic_sku,
                    "offer_id": offer["offer_id"],
                    "name": offer["name"],
                    "old_quantity": offer["available"],
                    "new_quantity": ic_quantity,
                }
            )

    missing_in_allegro = dict(
        sorted(
            (
                (sku, item)
                for sku, item in ic_office_stock.items()
                if sku not in matched_ic_skus and item["quantity"] > 0
            ),
            key=lambda pair: pair[1]["price"],
            reverse=True,
        )
    )

    return {
        "updates": updates,
        "unchanged": unchanged,
        "missing_in_allegro": missing_in_allegro,
    }


def write_missing_items_report(missing: dict[str, dict], path: str | Path = None) -> None:
    """
    Zapíše CSV so zoznamom tovaru na sklade bez zodpovedajúcej Allegro
    ponuky, zoradený podľa predajnej ceny zostupne (najdrahšie prvé) -
    priorita pre manuálne nahrávanie na Allegro. Poradie riadkov v
    `missing` (z `compute_diff`) sa zachováva.
    """
    report_path = Path(path or config.ALLEGRO_MISSING_ITEMS_REPORT)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(["Kód", "Názov", "Počet ks na sklade", "Predajná cena s DPH"])
        for sku, item in missing.items():
            writer.writerow([sku, item["name"], item["quantity"], f"{item['price']:.2f}"])


def sync_stock_to_allegro(
    ic_office_path: str | Path = None,
    allegro_offers: dict[str, dict] = None,
    apply: bool = True,
) -> dict:
    """
    Spustí celé porovnanie a (ak `apply=True`) úpravu skladovej
    dostupnosti na Allegro. Ak `allegro_offers` nie je zadané, načíta ich
    cez `allegro.fetch_active_offers()` (živé REST API - vyžaduje OAuth
    prístup). Pre porovnanie z CSV exportu použite
    `allegro.load_offers_from_csv()` a výsledok odovzdajte v tomto
    parametri (aktualizácia cez `apply=True` aj tak beží cez REST API,
    keďže na zápis je OAuth vždy potrebný).

    Vráti diff (pozri `compute_diff`) doplnený o skutočne vykonané zmeny
    v "updates"/"ended" (ak `apply=False`, ide o navrhované zmeny).
    """
    ic_office_stock = load_ic_office_stock(ic_office_path)
    print(f"Položiek v IC Office sklade: {len(ic_office_stock)}")

    if allegro_offers is None:
        allegro_offers = allegro.fetch_active_offers()
    print(f"Aktívnych ponúk na Allegro: {len(allegro_offers)}")

    diff = compute_diff(ic_office_stock, allegro_offers)

    ended = []
    applied_updates = []
    for change in diff["updates"]:
        if change["new_quantity"] == 0 and SYNC_END_OUT_OF_STOCK_OFFERS:
            if apply:
                allegro.end_offer(change["offer_id"])
            ended.append(change)
            print(f"[Allegro] {'Ukončená' if apply else 'NA UKONČENIE'} ponuka (0 ks): {change['sku']} - {change['name']}")
            continue

        if apply:
            allegro.update_offer_stock(change["offer_id"], change["new_quantity"])
        applied_updates.append(change)
        prefix = "[Allegro]" if apply else "[NÁVRH]"
        match_note = "" if change["sku"] == change["ic_office_kod"] else f" (~ IC Office '{change['ic_office_kod']}')"
        print(f"{prefix} {change['sku']}{match_note}: {change['old_quantity']} -> {change['new_quantity']} ks")

    missing = diff["missing_in_allegro"]
    if missing:
        write_missing_items_report(missing)
        print(
            f"\nTovar na sklade bez Allegro ponuky: {len(missing)} položiek "
            f"(zoradené podľa ceny, najdrahšie prvé) - report uložený do "
            f"{config.ALLEGRO_MISSING_ITEMS_REPORT}"
        )
    else:
        print("\nŽiadny tovar na sklade bez zodpovedajúcej Allegro ponuky.")

    return {
        "updated": applied_updates,
        "ended": ended,
        "missing": missing,
        "unchanged": diff["unchanged"],
    }


if __name__ == "__main__":
    sync_stock_to_allegro()
