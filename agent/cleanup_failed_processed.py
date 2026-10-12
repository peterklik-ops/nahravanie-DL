"""
Jednorazový pomocný skript - odstráni zo processed_*.json záznamy pre
doklady, ktoré VČERA (2026-10-12) zlyhali kvôli piatkovej aktualizácii
IC Office (pole "Zákazka" vo wizarde, teraz opravené), aby ich agent pri
najbližšom behu spracoval znova sám namiesto ručného dohrávania.

Bezpečnostná poistka: v DRY-RUN režime (predvolené) iba VYPÍŠE, ktoré
záznamy by zmazal - nič nezapíše. Skutočné zmazanie iba s --apply, po
tom, čo si výpis skontroluješ (aby sa omylom nezmazal záznam patriaci
inému, úspešne spracovanému dokladu - to by spôsobilo duplicitu v
sklade).

Porovnáva sa podreťazcovo (case-insensitive) oboma smermi, keďže uložený
"document_number" (text odkazu na portáli) sa nemusí presne zhodovať s
názvom stiahnutého súboru (napr. "DL26103548" vs "dl26103548.csv").

Použitie:
    python3 cleanup_failed_processed.py            # len vypíše, nič nezmení
    python3 cleanup_failed_processed.py --apply     # skutočne zmaže
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import config

NITECH_FAILED = [
    "26103548",
    "26103547",
    "26103546",
    "26103545",
    "26103544",
    "26103543",
    "26103541",
    "26103540",
    "26103539",
    "26103538",
    "26103537",
    "26103536",
]
EUROVAT_FAILED = [
    "2662267630",
]

NITECH_FILE = Path(config.DOWNLOAD_DIR).parent / "processed_nitech_delivery_notes.json"
EUROVAT_FILE = Path(config.DOWNLOAD_DIR).parent / "processed_eurovat_delivery_notes.json"


def _process_file(store_path: Path, failed_numbers: list[str], apply: bool) -> None:
    print(f"\n=== {store_path} ===")
    if not store_path.exists():
        print("  Súbor neexistuje - preskakujem.")
        return

    ids = json.loads(store_path.read_text(encoding="utf-8"))
    to_remove = []
    for id_ in ids:
        for number in failed_numbers:
            if number.lower() in id_.lower() or id_.lower() in number.lower():
                to_remove.append((id_, number))
                break

    if not to_remove:
        print("  Žiadna zhoda - nič na zmazanie (skontroluj, či sú čísla správne).")
        return

    print(f"  Nájdené zhody ({len(to_remove)}):")
    for id_, number in to_remove:
        print(f"    {id_!r}  (zodpovedá zlyhanému číslu {number!r})")

    if not apply:
        print("  DRY-RUN - nič sa nezmenilo. Spusti s --apply pre skutočné zmazanie.")
        return

    remaining = [id_ for id_ in ids if id_ not in {x[0] for x in to_remove}]
    store_path.write_text(json.dumps(sorted(remaining), ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  Zmazané. Zostáva {len(remaining)} záznamov (predtým {len(ids)}).")


def main() -> None:
    apply = "--apply" in sys.argv
    print("Režim:", "APPLY (skutočne mažem)" if apply else "DRY-RUN (len vypisujem)")
    _process_file(NITECH_FILE, NITECH_FAILED, apply)
    _process_file(EUROVAT_FILE, EUROVAT_FAILED, apply)


if __name__ == "__main__":
    main()
