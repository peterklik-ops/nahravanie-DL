"""
Porovná skladové zásoby z IC Office (CSV export) s aktívnymi ponukami na
Allegro a:
  1. upraví skladovú dostupnosť (počet kusov) na Allegro pri položkách,
     ktoré sa spárujú podľa kódu/SKU a majú iný počet kusov,
  2. voliteľne ukončí Allegro ponuky, ktoré sú v IC Office na 0 ks
     (SYNC_END_OUT_OF_STOCK_OFFERS - vypnuté predvolene, pozri POZOR
     v `allegro.end_offer`),
  3. tovar, ktorý JE na sklade v IC Office, ale NEMÁ zodpovedajúcu
     Allegro ponuku podľa kódu/SKU, zapíše do CSV reportu
     (config.ALLEGRO_MISSING_ITEMS_REPORT) - automatické vytvorenie
     ponuky nie je implementované, pozri `allegro.create_offer`.

Vstup: CSV export skladu z IC Office (Sklady -> Tovar -> export), cesta
config.IC_OFFICE_STOCK_CSV. Stĺpce sa nastavujú cez config.IC_OFFICE_STOCK_*.
"""

import csv
from pathlib import Path

import allegro
import config

# Ak True, Allegro ponuky pre tovar na 0 ks v IC Office sa rovno ukončia.
# Pozor: ukončenú ponuku Allegro API neumožňuje znova aktivovať - preto je
# toto predvolene vypnuté, kým sa nepotvrdí, že je to naozaj žiaduce.
SYNC_END_OUT_OF_STOCK_OFFERS = False


def load_ic_office_stock(csv_path: str | Path = None) -> dict[str, dict]:
    """
    Načíta CSV export skladu z IC Office a vráti mapu
    {sku: {"quantity": int, "name": str}}.
    """
    path = Path(csv_path or config.IC_OFFICE_STOCK_CSV)
    if not path.exists():
        raise FileNotFoundError(
            f"Súbor so skladom '{path}' neexistuje - stiahnite export z IC "
            "Office (Sklady -> Tovar -> export) a uložte ho na túto cestu, "
            "alebo upravte IC_OFFICE_STOCK_CSV v .env."
        )

    stock: dict[str, dict] = {}
    with path.open(encoding=config.IC_OFFICE_STOCK_CSV_ENCODING, newline="") as f:
        reader = csv.DictReader(f, delimiter=config.IC_OFFICE_STOCK_CSV_DELIMITER)
        missing_columns = {
            config.IC_OFFICE_STOCK_SKU_COLUMN,
            config.IC_OFFICE_STOCK_QUANTITY_COLUMN,
        } - set(reader.fieldnames or [])
        if missing_columns:
            raise ValueError(
                f"CSV '{path}' neobsahuje očakávané stĺpce {missing_columns}. "
                f"Nájdené stĺpce: {reader.fieldnames}. Upravte "
                "IC_OFFICE_STOCK_SKU_COLUMN / IC_OFFICE_STOCK_QUANTITY_COLUMN "
                "v .env podľa skutočného exportu."
            )

        for row in reader:
            sku = row[config.IC_OFFICE_STOCK_SKU_COLUMN].strip()
            if not sku:
                continue
            quantity_raw = row[config.IC_OFFICE_STOCK_QUANTITY_COLUMN].strip().replace(",", ".")
            try:
                quantity = int(float(quantity_raw))
            except ValueError:
                print(f"[UPOZORNENIE] Neplatné množstvo '{quantity_raw}' pre SKU {sku}, preskakujem.")
                continue
            name = row.get(config.IC_OFFICE_STOCK_NAME_COLUMN, "").strip()
            stock[sku] = {"quantity": quantity, "name": name}

    return stock


def write_missing_items_report(missing: dict[str, dict], path: str | Path = None) -> None:
    """Zapíše CSV so zoznamom tovaru na sklade bez zodpovedajúcej Allegro ponuky."""
    report_path = Path(path or config.ALLEGRO_MISSING_ITEMS_REPORT)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(["Kód", "Názov", "Počet ks na sklade"])
        for sku, item in sorted(missing.items()):
            writer.writerow([sku, item["name"], item["quantity"]])


def sync_stock_to_allegro(csv_path: str | Path = None) -> dict:
    """
    Spustí celý proces porovnania a úpravy. Vráti súhrn:
        {"updated": [...], "ended": [...], "missing": {...}, "unchanged": int}
    """
    ic_office_stock = load_ic_office_stock(csv_path)
    print(f"Položiek v IC Office sklade: {len(ic_office_stock)}")

    allegro_offers = allegro.fetch_active_offers()
    print(f"Aktívnych ponúk na Allegro: {len(allegro_offers)}")

    updated = []
    ended = []
    unchanged = 0

    for sku, offer in allegro_offers.items():
        stock_item = ic_office_stock.get(sku)
        ic_quantity = stock_item["quantity"] if stock_item else 0

        if offer["available"] == ic_quantity:
            unchanged += 1
            continue

        if ic_quantity == 0 and SYNC_END_OUT_OF_STOCK_OFFERS:
            allegro.end_offer(offer["offer_id"])
            ended.append({"sku": sku, "name": offer["name"]})
            print(f"[Allegro] Ukončená ponuka (0 ks v IC Office): {sku} - {offer['name']}")
            continue

        allegro.update_offer_stock(offer["offer_id"], ic_quantity)
        updated.append(
            {
                "sku": sku,
                "name": offer["name"],
                "old_quantity": offer["available"],
                "new_quantity": ic_quantity,
            }
        )
        print(f"[Allegro] {sku}: {offer['available']} -> {ic_quantity} ks")

    missing = {
        sku: item for sku, item in ic_office_stock.items()
        if sku not in allegro_offers and item["quantity"] > 0
    }
    if missing:
        write_missing_items_report(missing)
        print(
            f"Tovar na sklade bez Allegro ponuky: {len(missing)} položiek - "
            f"report uložený do {config.ALLEGRO_MISSING_ITEMS_REPORT}"
        )
    else:
        print("Žiadny tovar na sklade bez zodpovedajúcej Allegro ponuky.")

    return {"updated": updated, "ended": ended, "missing": missing, "unchanged": unchanged}


if __name__ == "__main__":
    sync_stock_to_allegro()
