# Agent: dodacie listy + kontrola predajných cien + sklad na Allegro

Automatizovaný proces:
1. Stiahne dodacie listy z **Nitech**, **Eurovat**, **InterCars**
2. Nahrá ich do **IC Office** (sekcia Sklad)
3. Načíta zákaznícku ponuku z InterCars a upraví predajné ceny v IC Office, ak sa líšia
4. Porovná sklad z **IC Office** (CSV export) s aktívnymi ponukami na **Allegro**,
   upraví počet kusov pri zhode a chýbajúci tovar (na sklade, no bez Allegro
   ponuky) zapíše do reportu - pozri sekciu [Sklad -> Allegro](#sklad---allegro) nižšie

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
# pridajte riadok pre denné spustenie o 6:00:
0 6 * * * cd /cesta/k/agent && venv/bin/python main.py >> /var/log/agent.log 2>&1
```

### B) GitHub Actions (scheduled workflow)
Ak nechcete spravovať vlastný server. Heslá sa uložia ako "Repository
Secrets" (šifrované, nikdy nie sú vidieť v logoch).

```yaml
# .github/workflows/agent.yml
on:
  schedule:
    - cron: "0 6 * * *"
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

## Sklad -> Allegro

Porovnáva skladové zásoby z IC Office s aktívnymi ponukami na Allegro a
párovanie robí podľa **kódu produktu (SKU)** - v IC Office ide o stĺpec
"Kód" v exporte tovaru, na Allegro o pole "ID zo systému predajcu"
(`external.id`) na ponuke. Aby sync fungoval, každá Allegro ponuka musí mať
toto pole vyplnené hodnotou zhodnou s kódom v IC Office.

### Nastavenie

1. **IC Office sklad (CSV export)**: momentálne sa nesťahuje automaticky.
   Pred každým behom manuálne stiahnite export tovaru zo sekcie
   **Sklady -> Tovar** v IC Office a uložte ho na cestu z
   `IC_OFFICE_STOCK_CSV` (predvolene `./downloads/sklad.csv`). Ak sa názvy
   stĺpcov v exporte líšia od predvolených ("Kód", "Sklad", "Názov"),
   upravte `IC_OFFICE_STOCK_*_COLUMN` v `.env`.
   - *Automatizácia sťahovania tohto exportu cez Playwright sa dá doplniť
     rovnako ako pri dodacích listoch, len treba nahrať presné selektory
     (`playwright codegen`) pre danú stránku exportu.*

2. **Allegro API prístup**:
   - Založte aplikáciu na https://apps.developer.allegro.pl/ (typ "Device
     aplikácia" alebo obdobný typ pre skripty bez webového backendu),
     doplňte `ALLEGRO_CLIENT_ID` a `ALLEGRO_CLIENT_SECRET` do `.env`.
   - Spustite jednorazovo `python allegro_device_login.py`, otvorte
     vypísanú URL, prihláste sa ako predajca a potvrďte prístup. Token sa
     uloží do `ALLEGRO_TOKEN_STORE` (`./allegro_token.json` - nikdy do
     gitu, je v `.gitignore`) a odvtedy sa už sám obnovuje.
   - Pre testovanie bez rizika zásahu do ostrých ponúk možno prepnúť na
     Allegro sandbox (`ALLEGRO_AUTH_URL` / `ALLEGRO_API_URL` v `.env`,
     hodnoty v komentári pri týchto premenných v `config.py`) - vyžaduje
     samostatnú sandboxovú appku a testovací predajcovský účet.

3. **Spustenie samostatne** (bez celého `main.py`):
   ```bash
   python stock_sync.py
   ```

### Čo sync robí a čo nie

- **Robí**: pri zhode SKU upraví počet kusov (`stock.available`) na Allegro
  podľa IC Office. Tovar na sklade bez zodpovedajúcej Allegro ponuky zapíše
  do CSV reportu (`ALLEGRO_MISSING_ITEMS_REPORT`).
- **Nerobí automaticky**: nevytvára nové Allegro ponuky pre chýbajúci
  tovar. Vytvorenie ponuky vyžaduje priradenie Allegro kategórie a jej
  povinných parametrov (značka, rozmer, OE číslo a pod. - líšia sa podľa
  kategórie), čo sa nedá bezpečne odvodiť automaticky. `allegro.create_offer`
  je pripravená ako miesto na doplnenie tejto logiky, keď bude jasné
  mapovanie kategórií.
- Ukončovanie ponúk pri 0 ks (`SYNC_END_OUT_OF_STOCK_OFFERS` v
  `stock_sync.py`) je predvolene **vypnuté**, pretože Allegro API
  neumožňuje ukončenú ponuku znova aktivovať (treba by sa vytvárať nová) -
  zapnite len ak je to naozaj žiaduce správanie.

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
