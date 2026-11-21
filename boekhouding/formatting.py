"""Geld en datums: parsen, afronden en opmaken (ook als template-filters)."""
import datetime as dt
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


def rhu(d) -> int:
    """Rond af op hele centen (half up)."""
    return int(Decimal(d).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def parse_money(value, default=None):
    """'1.234,56' / '1234.56' / '€ 12' -> centen (int)."""
    if value is None:
        return default
    s = str(value).strip().replace("€", "").replace(" ", "").replace("\xa0", "")
    if not s:
        return default
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return rhu(Decimal(s) * 100)
    except InvalidOperation:
        raise ValueError(f"Ongeldig bedrag: {value}")


def parse_qty(value) -> Decimal:
    s = str(value or "").strip().replace(" ", "")
    if not s:
        return Decimal(1)
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return Decimal(s)
    except InvalidOperation:
        raise ValueError(f"Ongeldig aantal: {value}")


def eur(cents):
    if cents is None:
        return ""
    cents = int(cents)
    euros, ct = divmod(abs(cents), 100)
    return "€ " + ("-" if cents < 0 else "") + f"{euros:,}".replace(",", ".") + f",{ct:02d}"


def money_input(cents):
    if cents is None or cents == "":
        return ""
    cents = int(cents)
    euros, ct = divmod(abs(cents), 100)
    return ("-" if cents < 0 else "") + f"{euros},{ct:02d}"


def fmt_qty(q):
    d = Decimal(str(q)).normalize()
    s = format(d, "f")
    return s.replace(".", ",")


def fmt_date(iso):
    if not iso:
        return ""
    try:
        return dt.date.fromisoformat(iso[:10]).strftime("%d-%m-%Y")
    except ValueError:
        return iso


def parse_date(value, default=None):
    try:
        return dt.date.fromisoformat(value).isoformat()
    except (TypeError, ValueError):
        return default


def quarter_range(year, q):
    start = dt.date(year, 3 * (q - 1) + 1, 1)
    end = dt.date(year + 1, 1, 1) if q == 4 else dt.date(year, 3 * q + 1, 1)
    return start.isoformat(), end.isoformat()


def current_quarter():
    t = dt.date.today()
    return t.year, (t.month - 1) // 3 + 1


TEMPLATE_FILTERS = {
    "eur": eur,
    "geld_invoer": money_input,
    "aantal": fmt_qty,
    "datum": fmt_date,
}
