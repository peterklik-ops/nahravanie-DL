"""
Jednorazový diagnostický skript - prejde WIZARD nahrávania dodacieho listu
(Sklad -> Tovar -> Naskladniť z dodacieho listu) presne tak, ako to robí
upload_delivery_note(), až po krok otvorenia poľa "Zákazka", ktoré od
piatkovej aktualizácie IC Office zlyháva na VŠETKÝCH dokladoch (timeout pri
`get_by_label("Zákazka").locator("b")`).

Namiesto slepého kliknutia vypíše skutočný HTML okolo poľa "Zákazka", aby
bolo vidieť, čo presne sa v aktualizácii zmenilo (rovnaký prístup, ktorý
odhalil predošlý problém s "Lu-Sy s.r.o.").

NEROBÍ žiadny zápis do skladu - zastaví sa pred krokom výberu zákazky aj
pred finálnym tlačidlom "Naskladniť", takže je bezpečné ho spustiť na
produkcii. Použije prvý CSV súbor, ktorý nájde v priečinku downloads (alebo
cestu zadanú ako argument).

Použitie:
    python3 debug_zakazka_field.py [cesta_k_csv]
"""

from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

import config
from portals import ic_office
from portals.base import new_context

SUPPLIER_NAME = "Autoparts - Nitech"
COLUMN_SETTINGS_VALUE = "62"


def _pick_csv_file() -> Path:
    if len(sys.argv) > 1:
        return Path(sys.argv[1])
    # Nitech súbory majú názov "dl<číslo>.csv" (potvrdené v chybových
    # hláškach, napr. "dl26103548.csv") - Eurovat súbory sú len číslo
    # (napr. "2662265190.csv" alebo "dodaci-list-2662265190.csv"). Keďže
    # skript ďalej používa SUPPLIER_NAME/COLUMN_SETTINGS_VALUE pre Nitech,
    # musí vybrať Nitech súbor, inak by mapovanie stĺpcov sedelo na iný
    # formát CSV a skreslilo by diagnostiku.
    nitech_candidates = sorted(Path(config.DOWNLOAD_DIR).glob("dl*.csv"))
    if nitech_candidates:
        return nitech_candidates[0]
    candidates = sorted(Path(config.DOWNLOAD_DIR).glob("*.csv"))
    if not candidates:
        raise SystemExit(f"Žiadny .csv súbor v {config.DOWNLOAD_DIR} - zadaj cestu ako argument.")
    return candidates[0]


def main() -> None:
    file_path = _pick_csv_file()
    print(f"Pouzivam CSV: {file_path}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=config.HEADLESS)
        try:
            context = new_context(browser, config.DOWNLOAD_DIR)
            page = context.new_page()
            ic_office.login(page)

            for attempt in range(3):
                try:
                    page.goto(ic_office.TOVAR_URL)
                    break
                except Exception:
                    if attempt == 2:
                        raise
                    page.wait_for_timeout(1000)
            page.get_by_role("link", name="Naskladniť z dodacieho listu").click()

            supplier_picker = page.locator("#snippet--suppliers").get_by_label("Výber dodávateľa")
            supplier_picker.click()
            page.get_by_role("treeitem", name=SUPPLIER_NAME).click(timeout=15000)
            page.locator("#import_export_dl_modal").get_by_text("OK").click()

            with page.expect_file_chooser() as file_chooser_info:
                page.get_by_text("Vybrať súbor").click()
            file_chooser_info.value.set_files(str(file_path))
            page.get_by_role("button", name="Ďalší").click()

            page.wait_for_function(
                """(value) => {
                    const select = document.querySelector('#columnSettings');
                    return !!select && Array.from(select.options).some((o) => o.value === value);
                }""",
                arg=COLUMN_SETTINGS_VALUE,
                timeout=8000,
            )
            page.evaluate(
                """(value) => {
                    const select = document.querySelector('#columnSettings');
                    select.value = value;
                    const option = select.options[select.selectedIndex];
                    const data = JSON.parse(option.dataset.set);
                    document.querySelectorAll('#table_columns tbody tr#data').forEach((row) => {
                        const idInput = row.querySelector('td#column_id input');
                        const fileSelect = row.querySelector('td#column_file select');
                        if (!idInput || !fileSelect) return;
                        const match = data.find((d) => d.column_id === idInput.value);
                        if (match) {
                            fileSelect.value = match.column_file;
                        }
                    });
                }""",
                COLUMN_SETTINGS_VALUE,
            )
            ic_office._click_next_checking_duplicate_warning(page)
            print("\nPo kroku 'Nastavenie stĺpcov' -> 'Ďalší', URL:", page.url)
            print("\n--- CELY VIDITELNY TEXT STRANKY (tento krok) ---")
            print(page.locator("body").inner_text()[:4000])
            print("--- KONIEC VYPISU TEXTU ---")

            # Marža - rovnaký krok ako v upload_delivery_note(), nech je
            # stav stránky čo najbližšie k reálnemu behu agenta.
            if page.locator("#margins_all").count() > 0:
                page.locator("#margins_all").select_option(index=0)
                page.locator("#margins_all").press("Tab")
                print("\nPo nastavení marže, URL:", page.url)
                print("\n--- CELY VIDITELNY TEXT STRANKY (po marzi) ---")
                print(page.locator("body").inner_text()[:4000])
                print("--- KONIEC VYPISU TEXTU ---")
            else:
                print("\n#margins_all sa na stránke NENAŠIEL (count=0).")

            print("\n--- DIAGNOSTIKA POLA 'Zakazka' ---")

            zakazka_label = page.get_by_label("Zákazka")
            count = zakazka_label.count()
            print(f"page.get_by_label('Zákazka').count() = {count}")
            for i in range(count):
                el = zakazka_label.nth(i)
                try:
                    html = el.evaluate("e => e.outerHTML")
                except Exception as exc:
                    html = f"<evaluate failed: {exc}>"
                print(f"\n[{i}] outerHTML:\n{html[:3000]}")

            b_inside = zakazka_label.locator("b")
            print(f"\npage.get_by_label('Zákazka').locator('b').count() = {b_inside.count()}")

            # Širšie hľadanie - čokoľvek na stránke s textom "Zákazka".
            broad = page.get_by_text("Zákazka", exact=False)
            print(f"\npage.get_by_text('Zákazka', exact=False).count() = {broad.count()}")
            for i in range(min(broad.count(), 15)):
                el = broad.nth(i)
                try:
                    html = el.evaluate("e => e.outerHTML")
                except Exception as exc:
                    html = f"<evaluate failed: {exc}>"
                print(f"\n[text-match {i}] outerHTML (max 800 znakov):\n{html[:800]}")

            # Stránka evidentne prešla kompletným prerobom (nové kroky
            # 1-4, nové polia "Číslo dodacieho listu"/"Dátum prijatia",
            # zoznam zákaziek sa teraz vypisuje priamo v texte stránky -
            # inak než predošlý treeitem strom). Vypísať skutočnú HTML
            # štruktúru okolo kľúčových textov, aby bolo vidieť, akým
            # prvkom (<select>? inému widgetu?) sa teraz "Vyberte zákazku"
            # a "Dodávateľ" renderujú.
            print("\n--- ID VŠETKÝCH Nette AJAX SNIPPETOV NA STRÁNKE ---")
            snippet_ids = page.evaluate(
                "() => Array.from(document.querySelectorAll('[id^=\"snippet-\"]')).map(e => e.id)"
            )
            print(snippet_ids)

            find_container_js = """(searchText) => {
                const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
                let node;
                while ((node = walker.nextNode())) {
                    if (node.textContent.trim() === searchText) {
                        let el = node.parentElement;
                        for (let i = 0; i < 2 && el.parentElement; i++) el = el.parentElement;
                        return el.outerHTML;
                    }
                }
                return null;
            }"""
            for marker in ["Dodávateľ:", "Vyberte zákazku", "Číslo dodacieho listu:", "Dátum prijatia/naskladnenia:"]:
                html = page.evaluate(find_container_js, marker)
                print(f"\n--- OKOLIE TEXTU {marker!r} (2 urovne nahor, max 2500 znakov) ---")
                print((html or "<NENAŠLO SA>")[:2500])

            print("\n--- VŠETKY <select> ELEMENTY NA STRÁNKE (id, name, počet <option>) ---")
            selects_info = page.evaluate(
                """() => Array.from(document.querySelectorAll('select')).map(s => ({
                    id: s.id, name: s.name, class: s.className, option_count: s.options.length
                }))"""
            )
            for info in selects_info:
                print(info)

            # Test OPRAVENEJ funkcie priamo (rovnaká ako v produkcii) -
            # vyberie prvú zákazku, ktorá sa reálne nachádza v zozname
            # #contract_all (podľa vyššie vypísaného textu), aby bolo
            # vidieť, či select_option() skutočne funguje na tomto
            # select2-zabalenom prvku.
            print("\n--- TEST OPRAVENEJ FUNKCIE _find_select_option_value / select_option ---")
            test_zakazka_number = "7455"  # existuje v zozname vyššie (2026/7455)
            value = ic_office._find_select_option_value(page, "contract_all", test_zakazka_number)
            print(f"_find_select_option_value(page, 'contract_all', {test_zakazka_number!r}) = {value!r}")
            if value is not None:
                page.locator("select#contract_all").select_option(value=value)
                selected_text = page.evaluate(
                    "() => document.querySelector('#contract_all').selectedOptions[0].textContent"
                )
                print(f"Po select_option, vybraný text: {selected_text!r}")
            else:
                print("NENAŠLO SA - over vzor/vstup.")

            # Pokracujeme o krok dalej (sklad + 'Dalsi'), aby bolo vidiet
            # Krok 3/4 - ESTE NEKLIKAME na 'Naskladnit'/'Ano', iba
            # nahliadame, ci tam nie je dalsia zmena struktury, ktoru by
            # bolo treba opravit pred nasadenim do ostreho behu.
            if page.locator("select#warehouse_all").count() > 0 and value is not None:
                page.locator("select#warehouse_all").select_option(ic_office.WAREHOUSE_OPTION_VALUES[ic_office.WAREHOUSE_MEDZISKLAD])
                ic_office._click_next_checking_duplicate_warning(page)
                print("\n--- PO 'Dalsi' (sklad+zakazka), URL:", page.url)
                print("\n--- CELY VIDITELNY TEXT STRANKY (dalsi krok, max 3000) ---")
                print(page.locator("body").inner_text()[:3000])
                print("--- KONIEC VYPISU TEXTU ---")
                print("\n*** TOTO JE POSLEDNY KROK, KTORY SKRIPT SPRAVI - NEKLIKA 'Naskladnit'/'Ano' ***")

            print("\n--- KONIEC DIAGNOSTIKY, zatváram bez uloženia ---")
            context.close()
        finally:
            browser.close()


if __name__ == "__main__":
    main()
