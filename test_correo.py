import smtplib
from email.message import EmailMessage

SMTP_HOST = "smtp-relay.brevo.com"
SMTP_PORT = 587
SMTP_USER = "afffd1001@smtp-brevo.com"
SMTP_PASSWORD = "bsksosty2mV0TUy"

FROM_EMAIL = "afffd1001@smtp-brevo.com"
TO_EMAIL = "edgar.kano@gmail.com"

msg = EmailMessage()
msg["Subject"] = "Prueba Brevo SMTP"
msg["From"] = FROM_EMAIL
msg["To"] = TO_EMAIL
msg.set_content("Correo enviado desde Python usando Brevo.")

with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as smtp:
    smtp.set_debuglevel(1)
    smtp.ehlo()
    smtp.starttls()
    smtp.ehlo()
    smtp.login(SMTP_USER, SMTP_PASSWORD)
    smtp.send_message(msg)

print("Correo enviado correctamente")