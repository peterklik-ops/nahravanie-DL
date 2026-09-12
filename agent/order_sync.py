"""
Synchronizácia objednávok podriadených zákazníkov z Nitechu do zákaziek
v IC Office.

Pre každú novú objednávku podriadeného zákazníka v Nitechu sa v IC Office
vytvorí zákazka (zákazník sa vyhľadá podľa mena z poznámky objednávky),
do poznámky zákazky sa uloží číslo objednávky (+ prípadná vlastná
poznámka zákazníka), aby sa k nej neskôr dali priradiť dodacie listy.

Keďže tento krok beží automaticky viackrát denne, sleduje sa v JSON
súbore (`PROCESSED_ORDERS_FILE`), ktoré čísla objednávok už boli
spracované, aby sa pre tú istú objednávku nevytvárali duplicitné zákazky.
"""

import json
from pathlib import Path
from playwright.sync_api import Page

import config
import notifier
from portals import nitech, ic_office

PROCESSED_ORDERS_FILE = Path(config.DOWNLOAD_DIR).parent / "processed_subcustomer_orders.json"


def _load_processed_order_numbers() -> set[str]:
    if not PROCESSED_ORDERS_FILE.exists():
        return set()
    return set(json.loads(PROCESSED_ORDERS_FILE.read_text(encoding="utf-8")))


def _mark_order_processed(order_number: str) -> None:
    processed = _load_processed_order_numbers()
    processed.add(order_number)
    PROCESSED_ORDERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    PROCESSED_ORDERS_FILE.write_text(
        json.dumps(sorted(processed), ensure_ascii=False, indent=2), encoding="utf-8"
    )


def sync_subcustomer_orders(nitech_page: Page, ic_office_page: Page) -> list[dict]:
    """
    Nájde nové objednávky podriadených zákazníkov v Nitechu (tie, ktorých
    číslo objednávky ešte nie je v `PROCESSED_ORDERS_FILE`) a pre každú
    vytvorí zákazku v IC Office. Vráti zoznam spracovaných objednávok.
    """
    orders = nitech.list_subcustomer_orders(nitech_page)
    processed = _load_processed_order_numbers()

    created: list[dict] = []
    failed: list[tuple[dict, Exception]] = []

    for order in orders:
        if order["order_number"] in processed:
            continue

        note_parts = [order["order_number"]]
        if order["custom_note"]:
            note_parts.append(order["custom_note"])

        try:
            ic_office.create_order_for_subcustomer(
                ic_office_page,
                customer_name=order["subcustomer_name"],
                note=" ".join(note_parts),
            )
        except Exception as exc:
            # Jedna zlyhaná objednávka (napr. nezaregistrovaný podriadený
            # zákazník) nesmie zablokovať spracovanie ostatných - skúsime
            # ju znova pri ďalšom behu (nezaznamenávame ju ako spracovanú).
            failed.append((order, exc))
            continue

        _mark_order_processed(order["order_number"])
        created.append(order)

    if failed:
        summary = "\n".join(
            f"{order['order_number']} ({order['subcustomer_name']}): {exc}"
            for order, exc in failed
        )
        notifier.send_alert(
            f"Agent: zlyhalo vytvorenie {len(failed)} zákaziek pre podriadených zákazníkov",
            summary,
        )

    return created
