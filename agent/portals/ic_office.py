"""
Modul pre IC Office (webová platforma) - nahratie dodacích listov na sklad
a úprava predajných cien.

STAV: KOSTRA - upload dodacích listov a cenové funkcie ešte treba doplniť.
Prihlásenie a vytvorenie zákazky pre podriadeného zákazníka sú hotové
(podľa playwright codegen nahrávky).
"""

from __future__ import annotations

import re
from pathlib import Path
from playwright.sync_api import Page

import config


def login(page: Page) -> None:
    # Priama URL prihlasovacieho formulára - odkaz "Prihlásiť" z domovskej
    # stránky (ic-office.sk/) nebol spoľahlivý, občas viedol na stránku
    # "Zabudnuté heslo" namiesto skutočného loginu.
    page.goto(config.IC_OFFICE_LOGIN_URL)
    page.get_by_placeholder("Email").fill(config.IC_OFFICE_USERNAME)
    page.get_by_placeholder("Heslo").fill(config.IC_OFFICE_PASSWORD)
    page.get_by_role("button", name="Prihlásiť").click()


# Sklad "medzisklad" - fixná hodnota, rovnaká pre podriadených zákazníkov
# aj pre dodacie listy s poznámkou konkrétnej zákazky (potvrdené). Pole
# "Sklad" vo wizarde nahrávania je treeitem widget (rovnaký ako "Výber
# dodávateľa"), nie <select> - preto ide o zobrazený názov, nie ID.
WAREHOUSE_MEDZISKLAD = "Medzisklad"

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


def upload_delivery_note(
    page: Page,
    file_path: Path,
    supplier_name: str,
    column_settings_value: str,
    zakazka_number: str,
    subcustomer_name: str | None = None,
    warehouse_name: str = WAREHOUSE_MEDZISKLAD,
) -> None:
    """
    Naskladní dodací list do IC Office (Sklad -> Tovar -> Naskladniť z
    dodacieho listu).

    `supplier_name` - presne podľa zoznamu "Výber dodávateľa" (napr.
    "EURO-VAT" alebo "Autoparts - Nitech").

    `column_settings_value` - uložený preset mapovania stĺpcov CSV, líši
    sa podľa dodávateľa (Eurovat "21", Nitech "62").

    `zakazka_number` - zobrazené číslo zákazky (napr. "2026/7212", presne
    v tvare, aký vracia find_zakazka_for_subcustomer()["number"]). Pole
    "Zákazka" vo wizarde je treeitem widget (rovnaký ako "Výber
    dodávateľa"), nie <select> - vyhľadáva sa podľa tohto zobrazeného textu.

    `subcustomer_name` - meno podriadeného zákazníka, podľa ktorého sa
    určí marža (MARGIN_OVERRIDES, inak DEFAULT_MARGIN_VALUE).

    `warehouse_name` - presne podľa zoznamu v poli "Sklad" (napr.
    "Medzisklad") - tiež treeitem widget, nie <select>.

    Výnimky (zatiaľ NEIMPLEMENTOVANÉ, riešime neskôr, dohodnuté):
    poznámka "servis" na dodacom liste -> tovar ide rovno do skladu
    "servis" namiesto na zákazku; záporná hodnota dodacieho listu
    (vratka) -> tovar ide do skladu "vratka".

    Poznámka: ak IC Office pri nahrávaní zobrazí varovanie, že dodací
    list s týmto číslom už bol nahraný (stalo sa to raz pri ručnom
    teste), táto funkcia to NERIEŠI automaticky - to by sa nemalo stať,
    keďže download_new_delivery_notes() už sleduje spracované súbory.
    """
    margin_percent = MARGIN_PERCENT_OVERRIDES.get(subcustomer_name, DEFAULT_MARGIN_PERCENT)
    margin_value = MARGIN_OPTION_VALUES[margin_percent]

    page.locator("a").filter(has_text="Sklady").first.click()
    page.get_by_role("link", name="Tovar").click()
    page.get_by_role("link", name="Naskladniť z dodacieho listu").click()

    page.locator("#snippet--suppliers").get_by_label("Výber dodávateľa").click()
    page.get_by_role("treeitem", name=supplier_name).click()
    page.locator("#import_export_dl_modal").get_by_text("OK").click()

    page.get_by_text("Vybrať súbor").click()
    page.get_by_label("Vybrať súbor").set_input_files(str(file_path))
    page.get_by_role("button", name="Ďalší").click()

    page.locator("#columnSettings").select_option(column_settings_value)
    page.get_by_role("button", name="Ďalší").click()

    page.locator("#margins_all").select_option(margin_value)
    page.locator("#margins_all").press("Tab")

    page.get_by_label("Zákazka").locator("b").click()
    page.get_by_role("treeitem", name=re.compile(re.escape(zakazka_number))).click()

    page.get_by_label("Sklad").locator("b").click()
    page.get_by_label("Sklad").click()
    page.get_by_role("treeitem", name=warehouse_name).click()

    page.get_by_role("button", name="Ďalší").click()

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

    page.locator("#state").select_option(CONTRACT_STATE_PRACUJE_SA)
    customer_filter = page.locator("#customer")
    customer_filter.fill(customer_name)
    customer_filter.press("Enter")

    rows = page.locator("#database_contracts tbody tr")
    matches = []

    for i in range(rows.count()):
        row = rows.nth(i)
        custzak = row.locator(".custzak")
        if custzak.count() == 0:
            continue

        div_id = custzak.get_attribute("id") or ""
        contract_id = div_id.removeprefix("div")
        if not contract_id:
            continue

        matches.append({
            "contract_id": contract_id,
            "number": custzak.locator("span").inner_text().strip(),
            "description": row.locator("td").nth(7).inner_text().strip(),
        })

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
    search_box = page.get_by_placeholder("Meno / Firma")
    search_box.fill(customer_name)
    search_box.press("Enter")

    # Podriadení zákazníci sa v drvivej väčšine opakujú - musia byť vopred
    # zaregistrovaní v Nitechu aj vytvorení ako klient v IC Office. Preto
    # vyžadujeme presnú zhodu mena: ak sa nenájde, ide pravdepodobne o
    # nezaregistrovaného/nového zákazníka a je bezpečnejšie to nahlásiť,
    # než zákazku omylom priradiť k inému (podobne pomenovanému) klientovi.
    customer_link = page.get_by_role("link", name=customer_name, exact=True)
    if customer_link.count() == 0:
        raise ValueError(
            f"Zákazník '{customer_name}' sa v IC Office nenašiel presnou zhodou mena "
            "- pravdepodobne nie je zaregistrovaný alebo sa meno nezhoduje s Nitechom."
        )
    customer_link.first.click()

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
