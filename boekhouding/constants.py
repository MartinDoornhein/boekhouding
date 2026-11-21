"""Vaste waarden: btw-situaties, kostencategorieën en standaardinstellingen."""
VAT_MODES = {
    "normaal": "Normaal – Nederlandse btw",
    "verlegd_nl": "Btw verlegd (binnenland)",
    "eu_b2b": "Dienst aan ondernemer in andere EU-lidstaat (btw verlegd)",
    "buiten_eu": "Klant buiten de EU (niet in NL belast)",
}
VAT_MODE_TEXT = {
    "verlegd_nl": "Btw verlegd.",
    "eu_b2b": "Btw verlegd / VAT reverse charge (art. 196 Richtlijn 2006/112/EG).",
    "buiten_eu": "Niet in Nederland belast / Not subject to Dutch VAT.",
}
EXPENSE_VAT_TYPES = {
    "nl": "Nederlandse btw (aftrekbaar)",
    "geen": "Geen of niet-aftrekbare btw",
    "eu_verlegd": "Verlegd – leverancier in andere EU-lidstaat",
    "buiten_eu_verlegd": "Verlegd – leverancier buiten de EU",
}
INVESTMENT_CAT = "Investering (≥ € 450, afschrijven)"
DEFAULT_CATEGORIES = [
    "Software & abonnementen", "Hardware (< € 450)", "Kantoorbenodigdheden",
    "Telefoon & internet", "Reiskosten", "Autokosten", "Opleiding & vakliteratuur",
    "Representatie", "Verzekeringen", "Bank- en betaalkosten", "Advieskosten",
    "Marketing & website", "Werkruimte", "Overig", INVESTMENT_CAT,
]
ALLOWED_RECEIPTS = {".pdf", ".jpg", ".jpeg", ".png", ".webp", ".heic", ".gif"}

DEFAULT_SETTINGS = {
    "bedrijfsnaam": "", "naam": "", "adres": "", "postcode": "", "plaats": "",
    "land": "Nederland", "email": "", "telefoon": "", "website": "",
    "kvk": "", "btw_id": "", "iban": "", "bic": "",
    "betaaltermijn": "30", "factuur_prefix": "",
    "factuur_voettekst": "",
    "mail_onderwerp": "Factuur {nummer} van {bedrijfsnaam}",
    "mail_tekst": ("Beste {klant},\n\nIn de bijlage vind je factuur {nummer} "
                   "van {bedrag}, te voldoen vóór {vervaldatum}.\n\n"
                   "Met vriendelijke groet,\n{naam}\n{bedrijfsnaam}"),
    "logo": "",
}
