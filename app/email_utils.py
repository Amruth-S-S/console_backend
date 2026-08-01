import asyncio
import smtplib
from email.message import EmailMessage

from .config import settings
from .schemas import BookingOut

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587


def _build_message(to_addr: str, subject: str, html_body: str, pdf_bytes: bytes, filename: str) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.EMAIL_USER
    msg["To"] = to_addr
    msg.set_content("This email requires an HTML-capable mail client to view.")
    msg.add_alternative(html_body, subtype="html")
    msg.add_attachment(pdf_bytes, maintype="application", subtype="pdf", filename=filename)
    return msg


def _send_sync(recipients: list[str], subject: str, html_body: str, pdf_bytes: bytes, filename: str) -> None:
    # Gmail displays app passwords in 4-4-4-4 groups for readability; the
    # actual credential has no spaces in it.
    password = settings.EMAIL_PASSWORD.replace(" ", "")
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as smtp:
        smtp.starttls()
        smtp.login(settings.EMAIL_USER, password)
        # One send per recipient (not a single multi-To message) so the
        # client and the company inbox each only see themselves in "To".
        for to_addr in recipients:
            smtp.send_message(_build_message(to_addr, subject, html_body, pdf_bytes, filename))


def _invoice_email_html(booking: BookingOut) -> str:
    return f"""
    <div style="font-family:Arial,Helvetica,sans-serif;color:#1e293b;line-height:1.5;">
      <h2 style="color:#0f2b45;margin-bottom:4px;">Booking Confirmed</h2>
      <p>Hi {booking.clientName or "there"},</p>
      <p>
        Thank you for booking <b>{booking.packageTitle or "your package"}</b> with
        Ambaari Tours and Travels. Your invoice is attached to this email.
      </p>
      <table style="border-collapse:collapse;margin:14px 0;font-size:14px;">
        <tr><td style="padding:3px 14px 3px 0;color:#64748b;">Invoice No.</td><td><b>{booking.invoiceNumber or "—"}</b></td></tr>
        <tr><td style="padding:3px 14px 3px 0;color:#64748b;">Invoice Date</td><td><b>{booking.invoiceDate or "—"}</b></td></tr>
        <tr><td style="padding:3px 14px 3px 0;color:#64748b;">Travel Date</td><td><b>{booking.travelDate or "—"}</b></td></tr>
        <tr><td style="padding:3px 14px 3px 0;color:#64748b;">Amount Collected</td><td><b>Rs. {booking.amount or "0"}</b></td></tr>
      </table>
      <p>We look forward to making your journey unforgettable!</p>
    </div>
    """


async def send_booking_invoice_email(booking: BookingOut, pdf_bytes: bytes, filename: str) -> None:
    recipients = []
    if booking.clientEmail.strip():
        recipients.append(booking.clientEmail.strip())
    if settings.COMPANY_EMAIL:
        recipients.append(settings.COMPANY_EMAIL)
    if not recipients:
        return

    subject = f"Booking Confirmation - Invoice #{booking.invoiceNumber or booking.id}"
    html_body = _invoice_email_html(booking)
    # smtplib is blocking — keep it off the event loop.
    await asyncio.to_thread(_send_sync, recipients, subject, html_body, pdf_bytes, filename)
