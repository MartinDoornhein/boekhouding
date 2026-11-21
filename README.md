# Boekhouding

Kleine, lokale boekhouding voor een eenmanszaak: kosten inboeken (met bon), facturen maken als PDF,
btw-aangifte per kwartaal en een jaaroverzicht voor de inkomstenbelasting. Python + Flask + SQLite,
geen abonnement, data blijft op je eigen schijf.

## Starten

- **macOS / Linux:** `./start.sh`
- **Windows:** dubbelklik `start.bat`
- Handmatig: `pip install -e .` en daarna `python -m boekhouding` (of `flask --app boekhouding run --port 5050`), open http://127.0.0.1:5050

Poort 5000 wordt op macOS gebruikt door AirPlay-ontvanger (lege, witte pagina), daarom draait de app op 5050.

Ga eerst naar **Instellingen** en vul je bedrijfsgegevens in (naam, adres, KvK, btw-id, IBAN).

## Werkwijze

**Facturen**
1. Klant aanmaken (eenmalig).
2. *+ Factuur* → regels invullen → *Opslaan als concept*. Een concept kun je nog wijzigen en als PDF bekijken.
3. *Definitief maken* → de factuur krijgt een doorlopend nummer (`2026-001`, `2026-002`, …) en is daarna niet meer te wijzigen.
4. *PDF downloaden* → *Mail opstellen* (opent je mailprogramma met tekst; PDF als bijlage toevoegen).
5. Bij betaling: *Betaald* met de datum van ontvangst.
6. Fout gemaakt? *Crediteren* maakt een creditnota (negatieve kopie) die je kunt aanpassen.

Btw-situaties per factuur: normaal (21% / 9% / 0%), btw verlegd binnenland, dienst aan EU-ondernemer
(btw verlegd, btw-id klant verplicht) en klant buiten de EU.

**Kosten**
Vul het totaalbedrag van de bon in. De app rekent excl. btw en de aftrekbare btw uit.
- *Nederlandse btw*: normale bon met btw.
- *Geen btw*: bijvoorbeeld een verzekering of bankkosten.
- *Verlegd – EU / buiten EU*: bijvoorbeeld Microsoft, Google, AWS of Adobe vanuit Ierland of de VS.
  Vul het factuurbedrag (zonder btw) in. De btw komt in 4a/4b en mag je tegelijk aftrekken in 5b.
- Categorie *Investering (≥ € 450)* telt niet mee als kosten in het jaaroverzicht. Die posten schrijf je af.

**Btw-aangifte**
Kies jaar en kwartaal. De kolom "invullen" geeft per rubriek het bedrag in hele euro's, zoals het op
Mijn Belastingdienst Zakelijk moet. Factureer je diensten aan EU-ondernemers, dan staat er ook een overzicht voor
de ICP-opgaaf. Het overzicht volgt het factuurstelsel (btw op factuurdatum), de standaard voor de meeste ondernemers.

**Jaaroverzicht**
Omzet, kosten per categorie, resultaat, investeringen, btw per kwartaal en openstaande debiteuren op 31-12.
Dat is de input voor de winst uit onderneming in je IB-aangifte.

## Data en back-up (bewaarplicht 7 jaar)

Alles staat in één SQLite-bestand: `data/boekhouding.db`, inclusief bonnen en logo. `data/` is de
Flask instance-map en staat in `.gitignore`. Een andere locatie kies je met `BOEKHOUDING_DATA=/pad/naar/map`.

- *Instellingen → Back-up downloaden* geeft een zip met de database en alle bonnen als losse bestanden.
- `flask --app boekhouding archive -o archief.zip` maakt dezelfde zip vanaf de commandline.
- Continue back-up naar Scaleway met Litestream, zie hieronder.

### Continue back-up naar Scaleway Object Storage (Litestream)

[Litestream](https://litestream.io) repliceert elke wijziging binnen ongeveer een seconde naar een bucket.
Je kunt 30 dagen terug naar elk willekeurig moment.

**1. Bucket en sleutel aanmaken (Terraform, eenmalig)**

```bash
cd infra/scaleway
cp terraform.tfvars.example terraform.tfvars     # kies een unieke bucketnaam
export SCW_ACCESS_KEY=... SCW_SECRET_KEY=... SCW_DEFAULT_ORGANIZATION_ID=...   # je eigen beheerderssleutel
terraform init && terraform apply
terraform output -raw env_file > ../../.env      # bucket, regio en Litestream-sleutel
```

Dit maakt het volgende aan:
- een **apart project**;
- een bucket met **versioning**: verwijderde of overschreven bestanden blijven nog 30 dagen terug te halen;
- een **applicatie-sleutel die alleen objecten in dat project mag lezen en schrijven**. Die sleutel kan versioning,
  lifecycle-regels en de bucket zelf niet aanpassen.

Lifecycle-regels: `boekhouding/` (de replica) ruimt oude versies na 30 dagen op. `archief/` wordt nooit
automatisch verwijderd en gaat na 30 dagen naar GLACIER.

> De Terraform-state bevat de geheime sleutel. `*.tfstate` staat daarom in `.gitignore`; bewaar de state veilig.

**2. Litestream installeren en starten**

```bash
brew install litestream     # of een release van github.com/benbjohnson/litestream
./start.sh
```

`start.sh` leest `.env`. Ontbreekt de database lokaal, dan haalt hij die eerst terug van Scaleway.
Daarna draait de app onder `litestream replicate`. Zonder `BOEKHOUDING_S3_BUCKET` start de app gewoon
zonder replicatie, met een waarschuwing. Litestream ondersteunt Windows niet officieel; `start.bat` start zonder replicatie.

> Laat nooit twee machines tegelijk naar dezelfde bucket repliceren (bijv. laptop én server).

**3. Herstel testen (doe dit meteen)**

Een back-up die je nooit hebt teruggezet, is nog geen back-up:

```bash
set -a; . ./.env; set +a
export BOEKHOUDING_DB=/tmp/herstel/boekhouding.db
litestream restore -config litestream.yml -o /tmp/herstel/boekhouding.db "$BOEKHOUDING_DB"
BOEKHOUDING_DATA=/tmp/herstel BOEKHOUDING_PORT=5051 .venv/bin/python -m boekhouding
```

Open http://127.0.0.1:5051 en controleer facturen en bonnen. Een eerder moment herstel je met
`-timestamp 2026-11-20T12:00:00Z`.

**4. Jaararchief**

Litestream bewaart 30 dagen. Voor de bewaarplicht van 7 jaar zet je eens per jaar (bijv. na de laatste
btw-aangifte) een archief in de bucket. Daarvoor is de AWS CLI nodig (`brew install awscli`):

```bash
scripts/archive.sh
```

Bewaar desgewenst ook een kopie op je NAS.

## Op de homelab draaien

```bash
BOEKHOUDING_HOST=0.0.0.0 BOEKHOUDING_PORT=5050 BOEKHOUDING_WACHTWOORD='iets-sterks' python -m boekhouding
```

Met `BOEKHOUDING_WACHTWOORD` vraagt de browser om een wachtwoord (gebruikersnaam maakt niet uit).
Stel de app niet open naar internet. Gebruik hem alleen op je LAN of via VPN/Tailscale, eventueel achter een reverse proxy met HTTPS.
Voor productiegebruik kun je `waitress` of `gunicorn` gebruiken in plaats van de ingebouwde server,
bijvoorbeeld `waitress-serve --call boekhouding:create_app`.

## Ontwikkelen

De opbouw volgt de [Flask-tutorial](https://flask.palletsprojects.com/en/stable/tutorial/layout/):

```
boekhouding/            het package (create_app in __init__.py)
├── db.py, schema.sql   SQLite-verbinding en schema (`flask --app boekhouding init-db`)
├── constants.py        btw-situaties, categorieën, standaardinstellingen
├── formatting.py       geld en datums parsen/opmaken
├── invoices.py         factuurberekeningen
├── btw_aangifte.py     btw-aangifte per kwartaal
├── pdf.py              factuur-PDF (ReportLab)
├── files.py            bonnen en logo als BLOB in de database
├── archief.py          back-up-zip en `flask archive`
├── rapportage.py       blueprint: overzicht, btw, jaar
├── klanten.py, facturen.py, kosten.py, instellingen.py   overige blueprints
├── templates/, static/
tests/                  pytest
infra/scaleway/         Terraform: project, bucket en sleutel voor Litestream
litestream.yml          Litestream-config (waarden uit .env)
scripts/archive.sh      jaararchief naar de bucket
data/                   lokale data (niet in git)
```

```bash
pip install -e ".[test]"
pytest
flask --app boekhouding run --port 5050 --debug
```

Eigen instellingen voor Flask kun je kwijt in `data/config.py` (wordt automatisch geladen).

## Wat er (bewust) niet in zit

- Directe bankkoppeling. Betalingen markeer je met de hand.
- Btw-aangifte rechtstreeks indienen. Je neemt de bedragen over in Mijn Belastingdienst Zakelijk.
- Afschrijvingen, KIA en kilometerregistratie. Die vul je in bij de IB-aangifte.
- KOR (kleineondernemersregeling).

Controleer de eerste kwartalen je uitkomsten naast Gekko, voordat je je abonnement opzegt.
