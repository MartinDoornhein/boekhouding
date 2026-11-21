# Boekhouding

Kleine, lokale boekhouding voor een eenmanszaak: kosten inboeken (met bon), facturen maken als PDF,
btw-aangifte per kwartaal en een jaaroverzicht voor de inkomstenbelasting. Python + Flask + SQLite,
geen abonnement, data blijft op je eigen schijf.

## Starten

- **macOS / Linux:** `./start.sh`
- **Windows:** dubbelklik `start.bat`
- Handmatig: `pip install -r requirements.txt` en daarna `python app.py`, open http://127.0.0.1:5000

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

Alles staat in de map `data/` naast de app: `boekhouding.db` (SQLite) en `bonnen/<jaar>/`.
- Zet `data/` in een map die automatisch geback-upt wordt, of
- gebruik *Instellingen → Back-up downloaden* (zip met database en alle bonnen), of
- kies zelf een locatie: `BOEKHOUDING_DATA=/pad/naar/map python app.py`.

De database is gewone SQLite, dus je kunt hem ook rechtstreeks bevragen of naar je eigen tooling exporteren.

## Op de homelab draaien

```bash
BOEKHOUDING_HOST=0.0.0.0 BOEKHOUDING_PORT=5000 BOEKHOUDING_WACHTWOORD='iets-sterks' python app.py
```

Met `BOEKHOUDING_WACHTWOORD` vraagt de browser om een wachtwoord (gebruikersnaam maakt niet uit).
Stel de app niet open naar internet. Gebruik hem alleen op je LAN of via VPN/Tailscale, eventueel achter een reverse proxy met HTTPS.
Voor productiegebruik kun je `waitress` of `gunicorn` gebruiken in plaats van de ingebouwde server.

## Wat er (bewust) niet in zit

- Directe bankkoppeling. Betalingen markeer je met de hand.
- Btw-aangifte rechtstreeks indienen. Je neemt de bedragen over in Mijn Belastingdienst Zakelijk.
- Afschrijvingen, KIA en kilometerregistratie. Die vul je in bij de IB-aangifte.
- KOR (kleineondernemersregeling).

Controleer de eerste kwartalen je uitkomsten naast Gekko, voordat je je abonnement opzegt.
