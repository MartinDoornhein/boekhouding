"""Factuur-PDF met ReportLab."""
import io
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (Image, Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle)

INK = colors.HexColor("#1f2933")
MUTED = colors.HexColor("#6b7280")
LINE = colors.HexColor("#d9dee5")
ACCENT = colors.HexColor("#1f4e79")


def _p(text, style):
    return Paragraph(escape(str(text or "")).replace("\n", "<br/>"), style)


def build_invoice_pdf(inv, cust, lines, totals, s, logo, helpers, vat_text=None, credit_of=None):
    eur, datum, aantal, line_amount = (helpers["eur"], helpers["datum"], helpers["aantal"],
                                       helpers["line_amount"])
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm,
                            topMargin=18 * mm, bottomMargin=24 * mm,
                            title=f"Factuur {inv['number'] or 'concept'}", author=s.get("bedrijfsnaam", ""))

    base = ParagraphStyle("base", fontName="Helvetica", fontSize=9.5, leading=13, textColor=INK)
    small = ParagraphStyle("small", parent=base, fontSize=8.5, leading=11.5, textColor=MUTED)
    right = ParagraphStyle("right", parent=base, alignment=TA_RIGHT)
    right_small = ParagraphStyle("rs", parent=small, alignment=TA_RIGHT)
    bold = ParagraphStyle("bold", parent=base, fontName="Helvetica-Bold")
    title = ParagraphStyle("title", parent=base, fontName="Helvetica-Bold", fontSize=20, leading=24,
                           textColor=ACCENT)
    company = ParagraphStyle("company", parent=base, fontName="Helvetica-Bold", fontSize=14, leading=18)

    story = []

    # Kop: logo/bedrijfsnaam links, gegevens rechts
    if logo:  # bytes (PNG/JPG)
        ir = ImageReader(io.BytesIO(logo))
        iw, ih = ir.getSize()
        h = 18 * mm
        w = min(iw * h / ih, 70 * mm)
        h = ih * w / iw
        left = Image(io.BytesIO(logo), width=w, height=h)
    else:
        left = _p(s.get("bedrijfsnaam"), company)
    addr = "\n".join(x for x in [
        s.get("bedrijfsnaam"), s.get("adres"),
        f"{s.get('postcode', '')} {s.get('plaats', '')}".strip(),
        s.get("email"), s.get("telefoon"), s.get("website")] if x)
    story.append(Table([[left, _p(addr, right_small)]], colWidths=[95 * mm, 75 * mm],
                       style=[("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                              ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    story.append(Spacer(1, 14 * mm))

    # Klant + factuurgegevens
    cust_lines = [cust["name"]]
    if cust["contact"]:
        cust_lines.append(f"t.a.v. {cust['contact']}")
    cust_lines += [cust["address"], f"{cust['postcode'] or ''} {cust['city'] or ''}".strip()]
    if cust["country"] and cust["country"].lower() not in ("nederland", "nl", "the netherlands"):
        cust_lines.append(cust["country"])
    cust_block = _p("\n".join(x for x in cust_lines if x), base)

    is_credit = bool(inv["credit_of"])
    label = "Creditfactuur" if is_credit else "Factuur"
    meta = [
        [_p("Factuurnummer", small), _p(inv["number"] or "CONCEPT", bold)],
        [_p("Factuurdatum", small), _p(datum(inv["date"]), base)],
    ]
    if not is_credit:
        meta.append([_p("Vervaldatum", small), _p(datum(inv["due_date"]), base)])
    if inv["period"]:
        meta.append([_p("Periode / levering", small), _p(inv["period"], base)])
    if credit_of:
        meta.append([_p("Credit op factuur", small), _p(credit_of, base)])
    if cust["vat_id"]:
        meta.append([_p("Btw-nummer klant", small), _p(cust["vat_id"], base)])
    meta_tbl = Table(meta, colWidths=[32 * mm, 43 * mm],
                     style=[("LEFTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 1),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 1)])
    story.append(Table([[cust_block, meta_tbl]], colWidths=[95 * mm, 75 * mm],
                       style=[("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    story.append(Spacer(1, 10 * mm))
    story.append(_p(label + ("" if inv["number"] else " (concept)"), title))
    story.append(Spacer(1, 5 * mm))

    # Regels
    normal = inv["vat_mode"] == "normaal"
    head = ["Omschrijving", "Aantal", "Prijs", "Btw", "Bedrag"] if normal else \
        ["Omschrijving", "Aantal", "Prijs", "", "Bedrag"]
    hstyle = ParagraphStyle("h", parent=small, fontName="Helvetica-Bold", textColor=MUTED)
    hright = ParagraphStyle("hr", parent=hstyle, alignment=TA_RIGHT)
    data = [[_p(head[0], hstyle)] + [_p(h, hright) for h in head[1:]]]
    for ln in lines:
        data.append([
            _p(ln["description"], base),
            _p(aantal(ln["quantity"]), right),
            _p(eur(ln["unit_price_cents"]), right),
            _p(f"{ln['vat_rate']}%" if normal else "", right),
            _p(eur(line_amount(ln)), right),
        ])
    lt = Table(data, colWidths=[86 * mm, 18 * mm, 26 * mm, 14 * mm, 26 * mm], repeatRows=1)
    lt.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, INK),
        ("LINEBELOW", (0, 1), (-1, -1), 0.4, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (0, -1), 0), ("RIGHTPADDING", (-1, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(lt)
    story.append(Spacer(1, 4 * mm))

    # Totalen
    tot = [[_p("Subtotaal", right), _p(eur(totals["subtotal"]), right)]]
    if normal:
        for rate, b, v in totals["groups"]:
            tot.append([_p(f"Btw {rate}% over {eur(b)}", right), _p(eur(v), right)])
    else:
        tot.append([_p("Btw", right), _p(eur(0), right)])
    tot.append([_p("Totaal", ParagraphStyle("tb", parent=right, fontName="Helvetica-Bold", fontSize=11)),
                _p(eur(totals["total"]), ParagraphStyle("tb2", parent=right, fontName="Helvetica-Bold",
                                                         fontSize=11))])
    story.append(Table(tot, colWidths=[144 * mm, 26 * mm], style=[
        ("LINEABOVE", (0, -1), (-1, -1), 0.8, INK), ("RIGHTPADDING", (-1, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, -1), (-1, -1), 5)]))
    story.append(Spacer(1, 8 * mm))

    if vat_text:
        story.append(_p(vat_text, bold))
        story.append(Spacer(1, 3 * mm))
    if inv["notes"]:
        story.append(_p(inv["notes"], base))
        story.append(Spacer(1, 3 * mm))

    if is_credit:
        pay = "Het bedrag van deze creditfactuur wordt verrekend of aan u terugbetaald."
    else:
        holder = s.get("bedrijfsnaam") or s.get("naam")
        pay = (f"Graag ontvangen wij het totaalbedrag van {eur(totals['total'])} uiterlijk "
               f"{datum(inv['due_date'])} op rekening {s.get('iban', '')} t.n.v. {holder}, "
               f"onder vermelding van factuurnummer {inv['number'] or '…'}.")
    story.append(_p(pay, base))
    if s.get("factuur_voettekst"):
        story.append(Spacer(1, 3 * mm))
        story.append(_p(s["factuur_voettekst"], small))

    footer_bits = [s.get("bedrijfsnaam"),
                   f"KvK {s['kvk']}" if s.get("kvk") else "",
                   f"Btw-id {s['btw_id']}" if s.get("btw_id") else "",
                   f"IBAN {s['iban']}" if s.get("iban") else "",
                   f"BIC {s['bic']}" if s.get("bic") else ""]
    footer = "  ·  ".join(b for b in footer_bits if b)
    draft = not inv["number"]

    def on_page(canvas, d):
        canvas.saveState()
        canvas.setStrokeColor(LINE)
        canvas.line(20 * mm, 16 * mm, A4[0] - 20 * mm, 16 * mm)
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(MUTED)
        canvas.drawCentredString(A4[0] / 2, 11 * mm, footer)
        canvas.drawRightString(A4[0] - 20 * mm, 6 * mm, f"Pagina {d.page}")
        if draft:
            canvas.setFont("Helvetica-Bold", 90)
            canvas.setFillColor(colors.Color(0.85, 0.2, 0.2, alpha=0.12))
            canvas.translate(A4[0] / 2, A4[1] / 2)
            canvas.rotate(35)
            canvas.drawCentredString(0, 0, "CONCEPT")
        canvas.restoreState()

    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    return buf.getvalue()
