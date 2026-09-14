# Agent: dodacie listy + kontrola predajných cien

Automatizovaný proces:
1. Stiahne dodacie listy z **Nitech**, **Eurovat**, **InterCars**
2. Nahrá ich do **IC Office** (sekcia Sklad)
3. Načíta zákaznícku ponuku z InterCars a upraví predajné ceny v IC Office, ak sa líšia

## Stav tohto projektu

Toto je **funkčná kostra**, nie hotový agent. Prihlasovacie a navigačné
selektory (miesta označené `# TODO`) treba doplniť podľa skutočného HTML
každej stránky. Bez tohto kroku skript nebude fungovať — potrebuje presne
vedieť, na ktoré tlačidlo kliknúť a do ktorého poľa napísať heslo.

## Krok 1: Dokončenie selektorov (odporúčam v Claude Code)

Pre každý portál (Nitech, Eurovat, InterCars, IC Office) spustite lokálne:

```bash
pip install playwright
playwright install chromium
playwright codegen https://www.nitech.sk/sk/prihlasenie
```

Otvorí sa prehliadač + nahrávacie okno. Keď sa prihlásite a prejdete na
dodacie listy presne tak, ako to robíte bežne, nástroj vygeneruje presný kód
(`page.fill(...)`, `page.click(...)`). Tento kód skopírujete do príslušného
súboru v `portals/`.

Toto je najrýchlejšie a najspoľahlivejšie urobiť v **Claude Code** – tam
viem s vami sedieť pri termináli, spúšťať `codegen` naživo, vidieť výstup
a rovno doplniť kód do súborov namiesto vás.

## Krok 2: Lokálne otestovanie

```bash
cd agent
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
playwright install chromium

cp .env.example .env
# vyplňte .env reálnymi prihlasovacími údajmi

# Pri ladení nastavte HEADLESS=false v .env, aby ste videli prehliadač naživo
python main.py
```

## Krok 3: Nasadenie na server (cloud, beží nezávisle)

Odporúčané možnosti, zoradené od najjednoduchšej:

### A) Malý VPS (napr. Hetzner, DigitalOcean, Azure/AWS mikro instancia) + cron
Najjednoduchšie a najlacnejšie riešenie pre tento typ úlohy.

```bash
# na serveri
git clone <vaš repozitár>
cd agent
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
playwright install --with-deps chromium

# heslá NIKDY do gitu - na serveri vytvorte .env priamo
nano .env

crontab -e
# Nitech aj Eurovat sa kontrolujú v rovnakých časoch (7:30, 10:30, 12:30,
# 13:30), každý pracovný deň (Po-Pia). main.py beží ako jeden skript pre
# všetky portály naraz - vďaka evidencii spracovaných dokladov je bezpečné
# spúšťať ho aj vtedy, keď niektorý z portálov nemá nič nové (jednoducho sa
# nič nestiahne).
30 7,10,12,13 * * 1-5 cd /cesta/k/agent && venv/bin/python main.py >> /var/log/agent.log 2>&1
```

### B) GitHub Actions (scheduled workflow)
Ak nechcete spravovať vlastný server. Heslá sa uložia ako "Repository
Secrets" (šifrované, nikdy nie sú vidieť v logoch).

Pozor: GitHub Actions cron beží v UTC, nie v slovenskom čase - a keďže
Slovensko strieda letný/zimný čas (UTC+2 / UTC+1), jeden pevný UTC cron
riadok sa časom "posunie" o hodinu. Nižšie je nastavené na letný čas
(UTC+2 → 5:30, 8:30, 10:30, 11:30 UTC = 7:30, 10:30, 12:30, 13:30 SELČ);
v zime treba časy posunúť o hodinu neskôr (6:30, 9:30, 11:30, 12:30 UTC),
alebo použiť VPS/cron s nastavenou lokálnou časovou zónou (variant A).

```yaml
# .github/workflows/agent.yml
on:
  schedule:
    # letný čas (UTC+2) - 7:30, 10:30, 12:30, 13:30 SELČ, Po-Pia
    - cron: "30 5,8,10,11 * * 1-5"
jobs:
  run-agent:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -r requirements.txt && playwright install --with-deps chromium
      - run: python main.py
        env:
          NITECH_USERNAME: ${{ secrets.NITECH_USERNAME }}
          NITECH_PASSWORD: ${{ secrets.NITECH_PASSWORD }}
          # ... ostatné secrets rovnako
```

### C) Serverless kontajner (AWS Lambda / Google Cloud Run s plánovačom)
Vhodné, ak už takúto infraštruktúru používate. Náročnejšie na nastavenie
kvôli veľkosti headless prehliadača — odporúčam až keď riešenie funguje
stabilne na variante A alebo B.

## Bezpečnosť a prevádzka — na čo myslieť

- **Heslá**: len cez `.env` / Secrets, nikdy v kóde alebo v gite (`.gitignore` je pripravený).
- **2FA / CAPTCHA**: ak niektorý z portálov vyžaduje dvojfaktorové overenie
  alebo captcha pri prihlásení, automatické prihlásenie sa skomplikuje —
  treba to overiť ako prvý krok pri nahrávaní selektorov.
- **Zmeny na webe dodávateľov**: ak si Nitech/Eurovat/InterCars/IC Office
  zmenia dizajn stránky, selektory sa môžu pokaziť. Odporúčam nastaviť
  upozornenia (`notifier.py`) tak, aby ste sa o zlyhaní dozvedeli hneď,
  nie až o týždeň neskôr.
- **Duplicitné sťahovanie**: momentálne kostra nesleduje, ktoré dodacie
  listy už boli spracované. Treba doplniť jednoduchú evidenciu (napr. JSON
  súbor so zoznamom už spracovaných čísel dokladov), aby sa ten istý
  dokument nesťahoval/nenahrával opakovane.
- **Podmienky používania portálov**: automatizovaný prístup k vlastnému
  dodávateľskému účtu je bežná firemná prax, ale ak máte pochybnosti,
  odporúčam si to potvrdiť s obchodným zástupcom Nitech/Eurovat/InterCars.

## Štruktúra projektu

```
agent/
├── config.py           # načítanie prihlasovacích údajov z .env
├── main.py             # hlavný orchestrátor (spúšťa všetko)
├── price_check.py       # porovnanie a úprava predajných cien
├── notifier.py          # upozornenia pri zlyhaní / zhrnutie zmien
├── portals/
│   ├── base.py          # zdieľané pomocné funkcie
│   ├── nitech.py         # TODO: doplniť selektory
│   ├── eurovat.py        # TODO: doplniť selektory
│   ├── intercars.py      # TODO: doplniť selektory + ponuka
│   └── ic_office.py      # TODO: doplniť selektory + úprava cien
├── requirements.txt
├── .env.example
└── .gitignore
```

## Ďalší krok

Odporúčam otvoriť **Claude Code** a spolu prejsť Krok 1 (nahrávanie
selektorov) postupne pre jeden portál za druhým — začnite napr. Nitechom,
otestujte, že sťahovanie a nahratie do IC Office reálne funguje, a až potom
pridajte Eurovat, InterCars a cenovú kontrolu.
