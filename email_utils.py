# email_utils.py
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.utils import formatdate
from email import encoders

def send_email_with_attachment(smtp_user: str, smtp_pass: str, to_addr: str, subject: str, filepath: str):
    msg = MIMEMultipart()
    msg["From"] = smtp_user
    msg["To"] = to_addr
    msg["Date"] = formatdate(localtime=True)
    msg["Subject"] = subject

    part = MIMEBase("application", "octet-stream")
    with open(filepath, "rb") as f:
        part.set_payload(f.read())
    encoders.encode_base64(part)
    part.add_header("Content-Disposition", f'attachment; filename="{filepath.split("/")[-1]}"')
    msg.attach(part)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(smtp_user, smtp_pass)
        server.sendmail(smtp_user, [to_addr], msg.as_string())
