"""
Modul pre IC Office (webová platforma) - nahratie dodacích listov na sklad
a úprava predajných cien.

STAV: KOSTRA - upload dodacích listov a cenové funkcie ešte treba doplniť.
Prihlásenie a vytvorenie zákazky pre podriadeného zákazníka sú hotové
(podľa playwright codegen nahrávky).
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

import config


def login(page: Page) -> None:
    # Priama URL prihlasovacieho formulára - odkaz "Prihlásiť" z domovskej
    # stránky (ic-office.sk/) nebol spoľahlivý, občas viedol na stránku
    # "Zabudnuté heslo" namiesto skutočného loginu.
    page.goto(config.IC_OFFICE_LOGIN_URL)
    page.get_by_placeholder("Email").fill(config.IC_OFFICE_USERNAME)
    page.get_by_placeholder("Heslo").fill(config.IC_OFFICE_PASSWORD)
    page.get_by_role("button", name="Prihlásiť").click()


# URL stránky "Tovar" (Sklady -> Tovar) - priama navigácia namiesto
# klikania cez rozbaľovacie menu, ktoré sa ukázalo ako nespoľahlivé
# (potvrdené v praxi opakovane, viď upload_delivery_note()).
TOVAR_URL = "https://ic-office.sk/warehouse/goods"

# Sklad "medzisklad" - fixná hodnota, rovnaká pre podriadených zákazníkov
# aj pre dodacie listy s poznámkou konkrétnej zákazky (potvrdené).
WAREHOUSE_MEDZISKLAD = "Medzisklad"

# Hodnoty <option value="..."> v <select id="warehouse_all"> (Krok 3 -
# Výber dát a skladov) podľa reálneho HTML - je to obyčajný <select>
# zabalený v select2 (rovnaký vzor ako #margins_all), NIE treeitem widget
# (na rozdiel od poľa "Zákazka" o krok skôr vo wizarde - potvrdené v praxi,
# pôvodný predpoklad bol nesprávny).
WAREHOUSE_OPTION_VALUES = {
    "Medzisklad": "231",
    "Poškodený tovar, neuznané reklamácie": "285",
    "Predaj ND": "392",
    "Reklamacie": "249",
    "Servis": "282",
    "Sklad": "256",
    "Vratky": "248",
}

# Hodnoty <option value="..."> v <select id="margins_all"> podľa percenta
# marže (zodpovedá atribútu data-margin="..." v reálnom HTML formulára).
MARGIN_OPTION_VALUES = {
    5: "5038",
    10: "5039",
    11.11: "13517",
    15: "5040",
    20: "5041",
    25: "5042",
    30: "5043",
    35: "5044",
    37: "21326",
    40: "5045",
    45: "5046",
    47: "5138",
    50: "5047",
    52.2: "13520",
    55: "5048",
    60: "5049",
    65: "5050",
    70: "5051",
    75: "5052",
    80: "5053",
    85: "5054",
    90: "5055",
    95: "5056",
    100: "5057",
}

# Marža podľa podriadeného zákazníka: 15 % pre všetkých, okrem výnimiek
# uvedených tu (Marek Jaszay má 10 %).
DEFAULT_MARGIN_PERCENT = 15
MARGIN_PERCENT_OVERRIDES = {
    "Marek Jaszay": 10,
}

# Marža pre bežné (nie podriadený zákazník) dodacie listy - dohodnuté,
# platí jednotne pre všetky tri prípady (zákazka podľa čísla v poznámke,
# poznámka "sklad", poznámka "servis").
REGULAR_MARGIN_PERCENT = 47

# Zobrazené názvy skladov použité pri bežných dodacích listoch bez
# zákazky - presne podľa WAREHOUSE_OPTION_VALUES.
WAREHOUSE_SKLAD = "Sklad"
WAREHOUSE_SERVIS = "Servis"


def _zakazka_search_pattern(zakazka_number: str) -> str:
    """
    Zostaví regex vzor na vyhľadanie zákazky v treeitem strome poľa
    "Zákazka". Pri plnom tvare (napr. "2026/7285", ako ho vracia
    find_zakazka_for_subcustomer()["number"]) sa iba escapuje "/" (viď
    upload_delivery_note - Playwright interne serializuje regex do tvaru
    /vzor/, neescapovaný "/" rozbíja parsovanie).

    Pri holom čísle (napr. "7276", vyťaženom priamo z poznámky bežného
    dodacieho listu podľa classify_regular_note()) sa navyše vyžaduje, aby
    bezprostredne nasledovalo po "/" a nepokračovalo ďalšou číslicou - inak
    by sa napr. "726" mylne zhodovalo aj so zákazkou "2026/7269" ako
    podreťazec.
    """
    if "/" in zakazka_number:
        return re.escape(zakazka_number).replace("/", r"\/")
    return r"\/" + re.escape(zakazka_number) + r"(?!\d)"


def _click_next_checking_duplicate_warning(page: Page) -> None:
    """
    Klikne na tlačidlo "Ďalší" a ošetrí varovanie "Zadané číslo dodacieho
    listu už v sklade existuje!" - IC Office ho zobrazuje NEKONZISTENTNE:
    niekedy ako samostatný krok PO úspešnom kliknutí (potvrdené v praxi po
    kroku nastavenia stĺpcov), inokedy AKO PRIAMY DÔSLEDOK samotného
    kliknutia - swal-overlay modal sa objaví okamžite a blokuje ten istý
    klik (potvrdené v praxi po kroku výberu skladu/zákazky - spôsobovalo
    to 30s nekonečný retry namiesto rozpoznania varovania). Nesmie sa cez
    toto varovanie prekliknúť ďalej - hrozila by reálna duplicita v sklade.
    """
    duplicate_warning = page.get_by_text(
        "Zadané číslo dodacieho listu už v sklade existuje"
    ).first

    def _raise_duplicate_error():
        page.get_by_role("button", name="OK").click()
        raise ValueError(
            "IC Office nahlásil, že dodací list s týmto číslom už v sklade "
            "existuje (pravdepodobne bol už nahraný iným spôsobom) - "
            "vyžaduje ručnú kontrolu, upload bol bezpečne prerušený."
        )

    try:
        page.get_by_role("button", name="Ďalší").click(timeout=5000)
    except PlaywrightTimeoutError as click_timeout:
        try:
            duplicate_warning.wait_for(state="visible", timeout=2000)
        except PlaywrightTimeoutError:
            raise click_timeout
        _raise_duplicate_error()
        return

    try:
        duplicate_warning.wait_for(state="visible", timeout=3000)
    except PlaywrightTimeoutError:
        pass
    else:
        _raise_duplicate_error()


def upload_delivery_note(
    page: Page,
    file_path: Path,
    supplier_name: str,
    column_settings_value: str,
    zakazka_number: str | None = None,
    subcustomer_name: str | None = None,
    warehouse_name: str = WAREHOUSE_MEDZISKLAD,
    margin_percent: float | None = None,
    set_margin: bool = True,
) -> None:
    """
    Naskladní dodací list do IC Office (Sklad -> Tovar -> Naskladniť z
    dodacieho listu).

    `supplier_name` - presne podľa zoznamu "Výber dodávateľa" (napr.
    "EURO-VAT" alebo "Autoparts - Nitech").

    `column_settings_value` - uložený preset mapovania stĺpcov CSV, líši
    sa podľa dodávateľa (Eurovat "21", Nitech "62").

    `zakazka_number` - zobrazené číslo zákazky (napr. "2026/7212", presne
    v tvare, aký vracia find_zakazka_for_subcustomer()["number"]), ALEBO
    holé číslo vyťažené z poznámky bežného dodacieho listu (napr. "7276",
    viď classify_regular_note()) - viď _zakazka_search_pattern(). Pole
    "Zákazka" vo wizarde je treeitem widget (rovnaký ako "Výber
    dodávateľa"), nie <select> - vyhľadáva sa podľa tohto zobrazeného textu.
    Ak je None, krok výberu zákazky sa celkom preskočí (dodací list ide
    priamo na sklad bez priradenia k zákazke - poznámka "sklad"/"servis").

    `subcustomer_name` - meno podriadeného zákazníka, podľa ktorého sa
    určí marža (MARGIN_PERCENT_OVERRIDES, inak DEFAULT_MARGIN_PERCENT) -
    len ak `margin_percent` nie je zadaný explicitne.

    `warehouse_name` - presne podľa zoznamu v poli "Sklad" (napr.
    "Medzisklad") - <select id="warehouse_all"> zabalený v select2
    (rovnaký vzor ako #margins_all), NIE treeitem widget.

    `margin_percent` - ak je zadaný, použije sa priamo (napr.
    REGULAR_MARGIN_PERCENT pre bežné dodacie listy) namiesto odvodenia
    z `subcustomer_name`. Irelevantné, ak `set_margin` je False.

    `set_margin` - ak False, krok nastavenia marže (#margins_all) sa
    celkom preskočí bez akéhokoľvek dotyku (potvrdené v praxi cez
    playwright codegen pre vratku/dobropis - marža sa tam nenastavuje
    vôbec, nie iba na 0 %). Používa sa pre záporné dodacie listy
    (vratka/dobropis, uznaná reklamácia).

    Poznámka k vratke/dobropisu (záporná hodnota dodacieho listu):
    vstupný bod aj dodávateľ sú ROVNAKÉ ako pri bežnom dodacom liste
    (potvrdené v praxi - "Naskladniť z dodacieho listu", "EURO-VAT"), mení
    sa iba `column_settings_value` (preset "NITECH DOBROPIS"/"EUROVAT
    Dobropis"), `set_margin=False` a `warehouse_name` ("Vratky", alebo
    "Reklamacie" pri poznámke "uznaná reklamácia"). Po nahratí treba
    RUČNE skontrolovať v "Pohyby tovaru / Dodacie listy" (Náhľad/editácia),
    že nahraté diely majú mínusový príznak - toto agent nerobí automaticky.

    Poznámka: ak IC Office pri nahrávaní zobrazí varovanie, že dodací
    list s týmto číslom už bol nahraný (stalo sa to raz pri ručnom
    teste), táto funkcia to NERIEŠI automaticky - to by sa nemalo stať,
    keďže download_new_delivery_notes() už sleduje spracované súbory.
    """
    margin_value = None
    if set_margin:
        if margin_percent is None:
            margin_percent = MARGIN_PERCENT_OVERRIDES.get(subcustomer_name, DEFAULT_MARGIN_PERCENT)
        margin_value = MARGIN_OPTION_VALUES[margin_percent]

    # Rozbaľovacie menu "Sklady" -> "Tovar" sa nerozbaľovalo spoľahlivo cez
    # hover+klik - potvrdené v praxi opakovane, vrátane prípadu, kde
    # zlyhal aj po 5 pokusoch (celkový 30s timeout, "Tovar" sa vôbec
    # neobjavilo). Namiesto krehkej interakcie s menu ide agent priamo na
    # URL stránky "Tovar" (potvrdené v praxi z HTML - href="/warehouse/goods").
    page.goto(TOVAR_URL)
    page.get_by_role("link", name="Naskladniť z dodacieho listu").click()

    page.locator("#snippet--suppliers").get_by_label("Výber dodávateľa").click()
    page.get_by_role("treeitem", name=supplier_name).click()
    page.locator("#import_export_dl_modal").get_by_text("OK").click()

    # Klik na "Vybrať súbor" spúšťa natívny OS dialóg na výber súboru
    # (potvrdené - macOS Finder okno) - ten by ako samostatné okno
    # operačného systému zablokoval ďalšiu automatizáciu. Zachytením cez
    # expect_file_chooser() sa dialóg nikdy reálne nezobrazí a súbor sa
    # nastaví priamo programovo.
    with page.expect_file_chooser() as file_chooser_info:
        page.get_by_text("Vybrať súbor").click()
    file_chooser_info.value.set_files(str(file_path))
    page.get_by_role("button", name="Ďalší").click()

    # Vyplnenie jednotlivých stĺpcov (napr. povinné "Kód tovaru") podľa
    # uloženého nastavenia rieši jQuery .change() handler na #columnSettings
    # (číta atribút data-set z vybranej <option> a nastavuje per-stĺpec
    # selecty). Ani natívna "change" udalosť (select_option()), ani
    # $(...).trigger('change') ho spoľahlivo nevyvolali - potvrdené v
    # praxi opakovane ("Kód tovaru je povinná položka"). #columnSettings
    # je súčasť Nette AJAX snippetu (#snippet--columns-settings), ktorý sa
    # mohol medzitým prekresliť a handler sa neprepojil na aktuálny prvok.
    #
    # Namiesto spoliehania sa na event handler zopakujeme priamo tú istú
    # logiku, akú handler vykonáva (podľa reálneho zdrojového kódu) -
    # nastavíme jednotlivé stĺpce ručne cez JS.
    #
    # #columnSettings je súčasť Nette AJAX snippetu, ktorý sa po kliknutí
    # na "Ďalší" ešte prekresľuje - `select.options[select.selectedIndex]`
    # bol raz `undefined`, čo znamená, že požadovaná <option> (napr.
    # value="62") v tej chvíli v DOM ešte neexistovala (potvrdené v praxi -
    # "Cannot read properties of undefined (reading 'dataset')"). Preto sa
    # najprv čaká, kým sa táto <option> reálne objaví, rovnako ako pri
    # iných AJAX snippetoch v tomto module.
    page.wait_for_function(
        """(value) => {
            const select = document.querySelector('#columnSettings');
            return !!select && Array.from(select.options).some((o) => o.value === value);
        }""",
        arg=column_settings_value,
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
        column_settings_value,
    )
    _click_next_checking_duplicate_warning(page)

    if set_margin:
        page.locator("#margins_all").select_option(margin_value)
        page.locator("#margins_all").press("Tab")

    # Ak zakazka_number nie je zadané (poznámka "sklad"/"servis"), krok
    # výberu zákazky sa celkom preskočí - tovar ide priamo na sklad.
    if zakazka_number is not None:
        page.get_by_label("Zákazka").locator("b").click()
        page.get_by_role(
            "treeitem", name=re.compile(_zakazka_search_pattern(zakazka_number))
        ).click()

    # id="warehouse_all" má aj obalový <th> tabuľky aj samotný <select> -
    # #warehouse_all preto nie je jednoznačný (potvrdené v praxi - strict
    # mode violation, 2 zhody).
    page.locator("select#warehouse_all").select_option(WAREHOUSE_OPTION_VALUES[warehouse_name])

    _click_next_checking_duplicate_warning(page)

    page.get_by_role("button", name="Naskladniť").click()
    page.locator("#importGoods").get_by_text("Áno").click()


# Hodnota <option> v stĺpcovom filtri #state (tabuľka Evidencia zákaziek)
# zodpovedajúca stavu "Pracuje sa" (potvrdené podľa reálneho HTML).
CONTRACT_STATE_PRACUJE_SA = "4"


def find_zakazka_for_subcustomer(
    page: Page, customer_name: str, custom_note: str | None = None
) -> dict:
    """
    Nájde v Evidencii zákaziek (Sklad -> Zákazky) zákazky zákazníka
    `customer_name` v stave "Pracuje sa", filtrované cez stĺpcové filtre
    tabuľky #database_contracts (#state select, #customer text input).

    Keďže jeden podriadený zákazník môže mať súčasne viac zákaziek so
    stavom "Pracuje sa", pri viacerých zhodách sa disambiguuje podľa
    toho, či stĺpec "Popis" (do ktorého create_order_for_subcustomer
    zapisuje "<číslo objednávky> <custom_note>") obsahuje `custom_note`.

    Vráti dict {contract_id, number, description} pre PRÁVE JEDNU
    nájdenú zákazku - contract_id je interné číselné ID záznamu (napr.
    "104227", z id="div104227" na .custzak elemente v riadku), number
    je zobrazené číslo zákazky (napr. "2026/7212") - v tomto tvare sa
    priamo použije ako `zakazka_number` v upload_delivery_note() (pole
    "Zákazka" vo wizarde je treeitem widget vyhľadávaný podľa textu,
    nie <select> podľa interného ID).

    Ak sa nenájde presne jedna zhoda, vyhodí ValueError - nesmie sa
    tichým odhadom priradiť dodací list k cudzej/nesprávnej zákazke
    (reálna chyba v sklade/účtovníctve).
    """
    page.get_by_role("link", name=" Zákazky").click()
    customer_filter = page.locator("#customer")
    state_filter = page.locator("#state")

    def _read_rows() -> list[dict]:
        rows = page.locator("#database_contracts tbody tr")
        found = []
        for i in range(rows.count()):
            row = rows.nth(i)
            try:
                custzak = row.locator(".custzak")
                if custzak.count() == 0:
                    continue

                div_id = custzak.get_attribute("id", timeout=2000) or ""
                contract_id = div_id.removeprefix("div")
                if not contract_id:
                    continue

                found.append({
                    "contract_id": contract_id,
                    "zakaznik": row.locator("td").nth(3).inner_text(timeout=2000).strip(),
                    "number": custzak.locator("span").inner_text(timeout=2000).strip(),
                    "description": row.locator("td").nth(7).inner_text(timeout=2000).strip(),
                })
            except PlaywrightTimeoutError:
                # Tabuľka sa mohla medzičasom prekresliť (AJAX) a tento
                # riadok medzitým zanikol/zmenil sa - preskočiť namiesto
                # pádu celého vyhľadávania (potvrdené v praxi - 30s
                # timeout na jednom riadku spadol celý beh).
                continue
        return found

    def _wait_for_change_then_stable(before_snapshot: tuple) -> list[dict]:
        # AJAX filtrovanie tejto tabuľky sa ukázalo ako nespoľahlivé na
        # pevné čakanie (networkidle aj reset+wait) - potvrdené v praxi
        # nekonzistentnými výsledkami pre to isté hľadanie v tom istom
        # behu. Preto sa najprv čaká, kým sa obsah SKUTOČNE ZMENÍ oproti
        # stavu pred akciou, a až potom sa kontroluje ustálenie (2x
        # rovnaký obsah za sebou) - pevné čakanie mohlo mylne prečítať
        # ešte neaktualizovaný stav ako "hotový".
        deadline = time.monotonic() + 8
        changed = False
        last_snapshot = before_snapshot
        stable_streak = 0
        rows: list[dict] = []
        while time.monotonic() < deadline:
            rows = _read_rows()
            snapshot = tuple(r["contract_id"] for r in rows)

            if not changed:
                if snapshot != before_snapshot:
                    changed = True
                    stable_streak = 1
                last_snapshot = snapshot
                page.wait_for_timeout(200)
                continue

            if snapshot == last_snapshot:
                stable_streak += 1
                if stable_streak >= 2:
                    break
            else:
                stable_streak = 0
            last_snapshot = snapshot
            page.wait_for_timeout(200)

        return rows

    def _search(name: str) -> list[dict]:
        # #state sa po AJAX prekreslení tabuľky (napr. po predošlom
        # hľadaní podľa mena) mohol ticho resetovať späť na "Všetky" -
        # potvrdené v praxi (počet zhôd narastal medzi behmi bez
        # zjavného dôvodu, až na nezmyselných 15). Preto sa nastavuje
        # nanovo pri KAŽDOM hľadaní, nie iba raz na začiatku.
        before_state = tuple(r["contract_id"] for r in _read_rows())
        state_filter.select_option(CONTRACT_STATE_PRACUJE_SA)
        _wait_for_change_then_stable(before_state)

        before_customer = tuple(r["contract_id"] for r in _read_rows())
        customer_filter.fill(name)
        customer_filter.press("Enter")
        rows = _wait_for_change_then_stable(before_customer)

        # Overiť, že stĺpec "Zákazník" naozaj obsahuje hľadané meno -
        # nielen spoliehať sa na to, že filter je nastavený správne.
        return [r for r in rows if name in r["zakaznik"]]

    matches = _search(customer_name)

    if not matches:
        # IC Office je zaužívaný formát "Priezvisko Meno" pre bežné osoby
        # (na rozdiel od Nitechu, ktorý dáva "Meno Priezvisko") - skúsi sa
        # preto aj obrátené poradie, len pri presne dvoch slovách (rovnaká
        # logika ako v create_order_for_subcustomer/_find_customer_link...).
        tokens = customer_name.split()
        if len(tokens) == 2:
            matches = _search(f"{tokens[1]} {tokens[0]}")

    if custom_note:
        with_matching_note = [m for m in matches if custom_note in m["description"]]
        if with_matching_note:
            matches = with_matching_note

    if len(matches) != 1:
        raise ValueError(
            f"Nepodarilo sa jednoznačne určiť zákazku v stave 'Pracuje sa' pre "
            f"zákazníka '{customer_name}' (nájdených zhôd: {len(matches)}, "
            f"custom_note={custom_note!r}) - vyžaduje ručnú kontrolu."
        )

    return matches[0]


# Hodnota <option> v stĺpcovom filtri #state zodpovedajúca "Všetky" stavy
# (potvrdené podľa reálneho HTML).
CONTRACT_STATE_ALL = "-2"


def order_already_has_zakazka(page: Page, order_number: str) -> bool:
    """
    Skontroluje v Evidencii zákaziek (naprieč VŠETKÝMI stavmi, nielen
    "Pracuje sa"), či už existuje zákazka, ktorej stĺpec "Popis" obsahuje
    toto číslo objednávky - buď presne v tvare z Nitechu (napr.
    "WO260093596"), alebo v staršom ručnom tvare bez predpony "WO" (napr.
    "260093596"), ktorý sa používal pri ručnom vytváraní zákaziek pred
    nasadením agenta.

    Bez tejto kontroly by sa pre objednávky, ktoré niekto medzičasom
    vybavil ručne (a teda nie sú v PROCESSED_ORDERS_FILE), vytvárali
    duplicitné zákazky - potvrdené v praxi (opakovane sa to stalo).
    """
    page.get_by_role("link", name=" Zákazky").click()
    page.locator("#state").select_option(CONTRACT_STATE_ALL)

    description_filter = page.locator("#description")

    def _search(value: str) -> bool:
        description_filter.fill(value)
        description_filter.press("Enter")
        page.wait_for_load_state("networkidle")

        if not value:
            return False

        # Neoverovať len prítomnosť nejakého riadku (.count() > 0), ale
        # skutočne prečítať Popis a potvrdiť, že hľadanú hodnotu naozaj
        # obsahuje - inak hrozí, že sa prečíta ešte "starý" výsledok
        # z predchádzajúceho hľadania (AJAX odpoveď doraziť neskoro),
        # čo by túto objednávku mylne označilo za už spracovanú a
        # zákazka by sa vôbec nevytvorila (potvrdené v praxi).
        rows = page.locator("#database_contracts tbody tr")
        for i in range(rows.count()):
            row = rows.nth(i)
            if row.locator(".custzak").count() == 0:
                continue
            popis = row.locator("td").nth(7).inner_text().strip()
            if value in popis:
                return True
        return False

    # Vyprázdniť filter pred prvým hľadaním - zabráni prelínaniu s
    # výsledkom z predchádzajúceho volania tejto funkcie pre inú
    # objednávku.
    _search("")

    candidates = {order_number}
    if order_number.startswith("WO"):
        candidates.add(order_number.removeprefix("WO"))

    for candidate in candidates:
        if _search(candidate):
            return True
        _search("")  # reset pred ďalším kandidátom / ďalším volaním

    return False


def _find_customer_link_by_exact_name(page: Page, name: str, timeout: int = 8000):
    """
    Vyhľadá zákazníka v tabuľke Klienti cez stĺpcový filter "Meno / Firma"
    a počká na presnú zhodu odkazu (s timeoutom). Vráti locator alebo None,
    ak sa v danom čase nenašiel.
    """
    search_box = page.get_by_placeholder("Meno / Firma")
    search_box.fill(name)
    search_box.press("Enter")

    # Filtrovanie tabuľky beží cez AJAX - .count() by mohol vidieť ešte
    # starý (nezaktualizovaný) stav tabuľky. Preto sa čaká na viditeľnosť
    # odkazu (s timeoutom), namiesto okamžitej kontroly počtu.
    link = page.get_by_role("link", name=name, exact=True).first
    try:
        link.wait_for(state="visible", timeout=timeout)
        return link
    except PlaywrightTimeoutError:
        return None


def create_order_for_subcustomer(page: Page, customer_name: str, note: str) -> None:
    """
    Vyhľadá zákazníka podľa mena, vytvorí zákazku, skopíruje pridelené
    číslo do názvu zákazky, vyplní poznámku (číslo objednávky z Nitechu
    a prípadná vlastná poznámka zákazníka) a nastaví stav "pracuje sa".
    """
    page.get_by_role("link", name=" Klienti ").click()

    # Horný vyhľadávač "Hľadať klienta / EČV" sa ukázal ako nespoľahlivý
    # (nenašiel zákazníka aj pri presnej zhode mena) - stĺpcový filter
    # "Meno / Firma" priamo v tabuľke funguje spoľahlivo (overené).
    #
    # Podriadení zákazníci sa v drvivej väčšine opakujú - musia byť vopred
    # zaregistrovaní v Nitechu aj vytvorení ako klient v IC Office. Preto
    # vyžadujeme presnú zhodu mena: ak sa nenájde, ide pravdepodobne o
    # nezaregistrovaného/nového zákazníka a je bezpečnejšie to nahlásiť,
    # než zákazku omylom priradiť k inému (podobne pomenovanému) klientovi.
    customer_link = _find_customer_link_by_exact_name(page, customer_name)

    if customer_link is None:
        # V IC Office je zaužívaný formát "Priezvisko Meno" pre bežné osoby
        # (na rozdiel od Nitechu, ktorý dáva "Meno Priezvisko") - skúsi sa
        # preto aj obrátené poradie, len pri presne dvoch slovách (firmy
        # s "s.r.o." a pod. majú viac slov a poradie sa im meniť nemá).
        tokens = customer_name.split()
        if len(tokens) == 2:
            reversed_name = f"{tokens[1]} {tokens[0]}"
            customer_link = _find_customer_link_by_exact_name(page, reversed_name)

    if customer_link is None:
        raise ValueError(
            f"Zákazník '{customer_name}' sa v IC Office nenašiel presnou zhodou mena "
            "(vrátane obráteného poradia meno/priezvisko) - pravdepodobne nie je "
            "zaregistrovaný alebo sa meno nezhoduje s Nitechom."
        )
    customer_link.click()

    page.get_by_role("link", name="+ Pridať zákazku").click()

    # "* Zakázkový list č.:" je textové pole s automaticky predvyplnenou
    # hodnotou v tvare "rok/číslo" (napr. "2026/7202") - do "Názov zákazky"
    # sa zapisuje len časť za lomítkom.
    order_sheet_value = page.get_by_role("textbox", name="* Zakázkový list č.:").input_value()
    match = re.search(r"/(\d+)\s*$", order_sheet_value)
    if not match:
        raise ValueError(
            f"Nepodarilo sa vyčítať číslo z poľa 'Zakázkový list č.' (hodnota: {order_sheet_value!r})"
        )
    order_number = match.group(1)

    page.get_by_role("textbox", name="* Názov zákazky:").fill(order_number)
    page.get_by_role("textbox", name="Popis zákazky:").fill(note)
    page.get_by_role("button", name="Pridať zákazku").click()

    # Otvorenie novovytvorenej zákazky - v zozname ju nájdeme podľa
    # prideleného čísla (zobrazuje sa v texte "2026/<číslo> - <číslo> -
    # Dátum: ...").
    page.get_by_text(re.compile(re.escape(order_number))).first.click()

    # Nastavenie stavu "pracuje sa"
    page.get_by_text("Stav", exact=True).click()
    status_frame = page.locator("#stateChange iframe").content_frame
    status_frame.get_by_text("Pracuje sa").click()
    status_frame.get_by_role("button", name="Zmeniť stav").click()


def get_current_sale_price(page: Page, sku: str) -> float:
    """Vráti aktuálnu predajnú cenu produktu v IC Office podľa kódu (SKU)."""
    # TODO: doplniť vyhľadanie produktu a čítanie ceny
    raise NotImplementedError


def update_sale_price(page: Page, sku: str, new_price: float) -> None:
    """Nastaví novú predajnú cenu produktu v IC Office podľa kódu (SKU)."""
    # TODO: doplniť vyhľadanie produktu, úpravu ceny, uloženie
    raise NotImplementedError
