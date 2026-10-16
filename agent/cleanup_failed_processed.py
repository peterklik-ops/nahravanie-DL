"""
Pomocný skript - odstráni zo processed_nitech_delivery_notes.json a
processed_eurovat_delivery_notes.json záznamy pre doklady, ktoré zlyhali
pri nahrávaní (napr. kvôli dočasnej chybe/aktualizácii IC Office, už
opravenej v kóde), aby ich agent pri najbližšom behu spracoval znova sám
namiesto ručného dohrávania.

Bezpečnostná poistka: v DRY-RUN režime (predvolené) iba VYPÍŠE, ktoré
záznamy by zmazal - nič nezapíše. Skutočné zmazanie iba s --apply, po
tom, čo si výpis skontroluješ (aby sa omylom nezmazal záznam patriaci
inému, úspešne spracovanému dokladu - to by spôsobilo duplicitu v
sklade).

Porovnáva sa podreťazcovo (case-insensitive) oboma smermi, keďže uložený
"document_number" (text odkazu na portáli) sa nemusí presne zhodovať s
názvom stiahnutého súboru (napr. "DL26103548" vs "dl26103548.csv"), a
prehľadáva sa VŽDY oba súbory (Nitech aj Eurovat) pre každé zadané číslo,
keďže skript sám nevie, ktorému dodávateľovi doklad patrí.

Použitie:
    python3 cleanup_failed_processed.py 26105734 2662269144
        # len vypíše zhody v oboch processed_*.json, nič nezmení
    python3 cleanup_failed_processed.py 26105734 2662269144 --apply
        # skutočne zmaže
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import config

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
        print("  Žiadna zhoda.")
        return

    print(f"  Nájdené zhody ({len(to_remove)}):")
    for id_, number in to_remove:
        print(f"    {id_!r}  (zodpovedá zadanému číslu {number!r})")

    if not apply:
        print("  DRY-RUN - nič sa nezmenilo. Spusti s --apply pre skutočné zmazanie.")
        return

    remaining = [id_ for id_ in ids if id_ not in {x[0] for x in to_remove}]
    store_path.write_text(json.dumps(sorted(remaining), ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  Zmazané. Zostáva {len(remaining)} záznamov (predtým {len(ids)}).")


def main() -> None:
    args = sys.argv[1:]
    apply = "--apply" in args
    numbers = [a for a in args if a != "--apply"]

    if not numbers:
        raise SystemExit(
            "Zadaj aspoň jedno číslo dokladu, napr.:\n"
            "  python3 cleanup_failed_processed.py 26105734 2662269144"
        )

    print("Režim:", "APPLY (skutočne mažem)" if apply else "DRY-RUN (len vypisujem)")
    print("Hľadané čísla:", numbers)
    _process_file(NITECH_FILE, numbers, apply)
    _process_file(EUROVAT_FILE, numbers, apply)


if __name__ == "__main__":
    main()
