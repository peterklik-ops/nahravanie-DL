"""
Porovná zákaznícku ponuku z InterCars s aktuálnymi predajnými cenami
v IC Office a upraví ceny, ktoré sa líšia.

Bezpečnostná poistka: MARGIN_TOLERANCE zabráni tomu, aby sa cena menila
pri zanedbateľných rozdieloch (napr. o 1 cent kvôli zaokrúhľovaniu).
"""

from playwright.sync_api import Page

from portals import ic_office

# Percentuálna odchýlka, pri ktorej sa cena ešte NEupravuje (0.5 %)
MARGIN_TOLERANCE = 0.005


def sync_prices(page: Page, offer_prices: dict[str, float]) -> list[dict]:
    """
    Pre každý produkt v `offer_prices` porovná cenu s IC Office.
    Ak sa líši nad toleranciu, upraví ju a zaznamená zmenu.

    Vráti zoznam zmien pre logovanie/notifikáciu, napr.:
        [{"sku": "ABC123", "old_price": 10.50, "new_price": 11.20}, ...]
    """
    changes = []

    for sku, offer_price in offer_prices.items():
        try:
            current_price = ic_office.get_current_sale_price(page, sku)
        except NotImplementedError:
            raise
        except Exception as exc:
            # Produkt sa možno v IC Office nenašiel - preskočiť a zalogovať
            print(f"[UPOZORNENIE] Nepodarilo sa nájsť cenu pre {sku}: {exc}")
            continue

        if current_price == 0:
            continue

        diff_ratio = abs(current_price - offer_price) / current_price
        if diff_ratio > MARGIN_TOLERANCE:
            ic_office.update_sale_price(page, sku, offer_price)
            changes.append(
                {"sku": sku, "old_price": current_price, "new_price": offer_price}
            )

    return changes
