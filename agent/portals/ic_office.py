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

from .. import config


def login(page: Page) -> None:
    page.goto(config.IC_OFFICE_LOGIN_URL)
    page.get_by_role("link", name="Prihlásiť").click()
    page.get_by_placeholder("Email").fill(config.IC_OFFICE_USERNAME)
    page.get_by_placeholder("Heslo").fill(config.IC_OFFICE_PASSWORD)
    page.get_by_role("button", name="Prihlásiť").click()


def upload_delivery_note(page: Page, file_path: Path) -> None:
    """
    Prejde do sekcie Sklad a nahrá súbor dodacieho listu.
    """
    # TODO: doplniť navigáciu do sekcie Sklad + nahratie súboru, napr.:
    # page.click('a:has-text("Sklad")')
    # page.click('button:has-text("Nahrať dodací list")')
    # page.set_input_files('input[type="file"]', str(file_path))
    # page.click('button:has-text("Potvrdiť")')
    # page.wait_for_load_state("networkidle")
    raise NotImplementedError("Doplňte logiku nahrávania dodacieho listu do IC Office")


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

    # "* Zakázkový list č.:" zobrazuje automaticky pridelené číslo v tvare
    # "rok/číslo" (napr. "2026/7202") - do "Názov zákazky" sa zapisuje len
    # časť za lomítkom.
    order_sheet_text = page.get_by_text("Zakázkový list č.").first.inner_text()
    match = re.search(r"(\d+)\s*$", order_sheet_text)
    if not match:
        raise ValueError(
            f"Nepodarilo sa vyčítať číslo zo 'Zakázkový list č.' (text: {order_sheet_text!r})"
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
