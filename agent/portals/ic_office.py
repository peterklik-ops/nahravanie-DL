"""
Modul pre IC Office (webová platforma) - nahratie dodacích listov na sklad
a úprava predajných cien.

STAV: KOSTRA - upload dodacích listov a cenové funkcie ešte treba doplniť.
Prihlásenie a vytvorenie zákazky pre podriadeného zákazníka sú hotové
(podľa playwright codegen nahrávky).
"""

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
# aj pre dodacie listy s poznámkou konkrétnej zákazky (potvrdené).
WAREHOUSE_MEDZISKLAD = "231"

# Marža podľa podriadeného zákazníka: 15 % pre všetkých, okrem výnimiek
# uvedených tu (napr. Marek Jaszay má 10 %).
# TODO: doplniť skutočnú hodnotu <option value="..."> pre 10 % maržu -
# "???" je len placeholder, kým nepošlete presný select_option riadok.
DEFAULT_MARGIN_VALUE = "5040"  # 15 % (potvrdené z reálnej nahrávky)
MARGIN_OVERRIDES = {
    "Marek Jaszay": "???",  # TODO: 10 % - doplniť skutočné value
}


def upload_delivery_note(
    page: Page,
    file_path: Path,
    supplier_name: str,
    column_settings_value: str,
    contract_option_value: str,
    subcustomer_name: str | None = None,
    warehouse_value: str = WAREHOUSE_MEDZISKLAD,
) -> None:
    """
    Naskladní dodací list do IC Office (Sklad -> Tovar -> Naskladniť z
    dodacieho listu).

    `supplier_name` - presne podľa zoznamu "Výber dodávateľa" (napr.
    "EURO-VAT" alebo "Autoparts - Nitech").

    `column_settings_value` - uložený preset mapovania stĺpcov CSV, líši
    sa podľa dodávateľa (Eurovat "21", Nitech "62").

    `contract_option_value` - interné ID zákazky (hodnota <option> v
    #contract_0, NIE zobrazené číslo zákazky ako "7193").
    TODO: automatické párovanie dodacieho listu na správnu zákazku
    (vytvorenú v order_sync.py) ešte nie je navrhnuté - túto hodnotu
    musí zatiaľ dodať volajúci (napr. na základe ručnej kontroly).

    `subcustomer_name` - meno podriadeného zákazníka, podľa ktorého sa
    určí marža (MARGIN_OVERRIDES, inak DEFAULT_MARGIN_VALUE).

    Výnimky (zatiaľ NEIMPLEMENTOVANÉ, riešime neskôr, dohodnuté):
    poznámka "servis" na dodacom liste -> tovar ide rovno do skladu
    "servis" namiesto na zákazku; záporná hodnota dodacieho listu
    (vratka) -> tovar ide do skladu "vratka".

    Poznámka: ak IC Office pri nahrávaní zobrazí varovanie, že dodací
    list s týmto číslom už bol nahraný (stalo sa to raz pri ručnom
    teste), táto funkcia to NERIEŠI automaticky - to by sa nemalo stať,
    keďže download_new_delivery_notes() už sleduje spracované súbory.
    """
    margin_value = MARGIN_OVERRIDES.get(subcustomer_name, DEFAULT_MARGIN_VALUE)

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
    page.locator("#contract_0").select_option(contract_option_value)
    page.locator("#warehouse_0").select_option(warehouse_value)
    page.get_by_role("button", name="Ďalší").click()

    page.get_by_role("button", name="Naskladniť").click()
    page.locator("#importGoods").get_by_text("Áno").click()


def create_order_for_subcustomer(page: Page, customer_name: str, note: str) -> None:
    """
    Vyhľadá zákazníka podľa mena, vytvorí zákazku, skopíruje pridelené
    číslo do názvu zákazky, vyplní poznámku (číslo objednávky z Nitechu
    a prípadná vlastná poznámka zákazníka) a nastaví stav "pracuje sa".
    """
    page.get_by_role("link", name=" Klienti ").click()

    search_box = page.get_by_role("textbox", name="Hľadať klienta / EČV")
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
