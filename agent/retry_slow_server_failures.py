"""
Pomocný skript - prehľadá log z behu agenta (/var/log/agent.log) a sám
rozpozná a vyčistí IBA tie zlyhané doklady, ktoré zjavne zlyhali na známy
"server bol pomalý" problém (výber dodávateľa zostal "not visible" aj po
60 sekundách čakania - pozri supplier_picker.click(timeout=60000) v
ic_office.upload_delivery_note()).

Pre KAŽDÚ inú chybu (čokoľvek, čo nemá presne tento podpis) skript nič
nerobí a vypíše ju osobitne ako "VYŽADUJE KONTROLU" - takéto doklady si
treba so mnou (Claude) prebrať, mohlo by ísť o nový/iný problém.

Bezpečnostná poistka rovnaká ako v cleanup_failed_processed.py: v
DRY-RUN režime (predvolené) iba vypíše, čo by zmazal. Skutočné zmazanie
iba s --apply.

Použitie:
    python3 retry_slow_server_failures.py
        # čítaš z /var/log/agent.log (dry-run)
    python3 retry_slow_server_failures.py /cesta/k/inemu.log
    python3 retry_slow_server_failures.py --apply
        # skutočne vyčistí rozpoznané "server bol pomalý" doklady
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from cleanup_failed_processed import NITECH_FILE, EUROVAT_FILE, _process_file

DEFAULT_LOG_PATH = Path("/var/log/agent.log")

# Podpis zlyhania musí obsahovať OBOJE, inak ho nepovažujeme za rozpoznaný
# "server bol pomalý" prípad (bezpečnejšie nerozpoznať a nechať na ručnú
# kontrolu, než omylom zmazať záznam patriaci inej, neznámej chybe).
SIGNATURE_PARTS = ("supplier_picker.click(timeout=60000)", "element is not visible")

FAILURE_BLOCK_RE = re.compile(
    r"^\[CHYBA\] Zlyhalo nahratie (?P<filename>\S+):\n(?P<traceback>.*?)(?=^\[|\Z)",
    re.MULTILINE | re.DOTALL,
)


def _find_failure_blocks(log_text: str) -> list[tuple[str, str]]:
    return [(m.group("filename"), m.group("traceback")) for m in FAILURE_BLOCK_RE.finditer(log_text)]


def main() -> None:
    args = sys.argv[1:]
    apply = "--apply" in args
    paths = [a for a in args if a != "--apply"]
    log_path = Path(paths[0]) if paths else DEFAULT_LOG_PATH

    if not log_path.exists():
        raise SystemExit(f"Log súbor sa nenašiel: {log_path}")

    log_text = log_path.read_text(encoding="utf-8", errors="replace")
    blocks = _find_failure_blocks(log_text)

    if not blocks:
        print(f"V {log_path} sa nenašiel žiadny '[CHYBA] Zlyhalo nahratie ...' záznam.")
        return

    recognized: list[str] = []
    unrecognized: list[str] = []

    for filename, tb in blocks:
        if all(part in tb for part in SIGNATURE_PARTS):
            recognized.append(filename)
        else:
            unrecognized.append(filename)

    print("Režim:", "APPLY (skutočne mažem)" if apply else "DRY-RUN (len vypisujem)")
    print(f"Log: {log_path}\n")

    if recognized:
        print(f"Rozpoznané ako 'server bol pomalý' ({len(recognized)}):")
        for name in recognized:
            print(f"  - {name}")
        print()
        numbers = [Path(name).stem for name in recognized]
        _process_file(NITECH_FILE, numbers, apply)
        _process_file(EUROVAT_FILE, numbers, apply)
    else:
        print("Žiadny zo zlyhaných dokladov nezodpovedá známemu 'server bol pomalý' podpisu.")

    if unrecognized:
        print(f"\nNEROZPOZNANÉ, VYŽADUJÚ KONTROLU ({len(unrecognized)}) - tieto som NEZMAZAL,")
        print("pošli mi ich chybový výpis z logu:")
        for name in unrecognized:
            print(f"  - {name}")


if __name__ == "__main__":
    main()
