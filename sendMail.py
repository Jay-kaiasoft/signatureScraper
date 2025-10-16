import json
import random
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# Load messages from JSON
with open("messages.json", "r", encoding="utf-8") as f:
    messages = json.load(f)

fromEmails = [
    {
        "email": "webzoidsolution@gmail.com",
        "password": "fdee tasv dsop rzwr",
        "protocol": "imaps",
        "smtpServer": "smtp.gmail.com",      # SMTP, not IMAP
        "smtpPort": 465,
        "maxMessages": 12
    },
    #   {
    #     "email": "dhruvdobariya04@yahoo.com",
    #     "password": "sfcynsioclascrbl",
    #     "protocol": "imaps",
    #     "smtpServer": "smtp.mail.yahoo.com",  # SMTP, not IMAP
    #     "smtpPort": 465,
    #     "maxMessages":12
    # },
]

toEmails = [
    "webzoidsolution@gmail.com",
    # "dhruvdobariya04@yahoo.com",    
]

# Send HTML email function
def send_html_email(subject, html_content, from_email, password, to_email, smtp_server, smtp_port, use_ssl=True):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_email
    msg["To"] = to_email
    msg.attach(MIMEText(html_content, "html"))

    try:
        if use_ssl:
            server = smtplib.SMTP_SSL(smtp_server, smtp_port)
        else:
            server = smtplib.SMTP(smtp_server, smtp_port)
            server.starttls()

        server.login(from_email, password)
        server.sendmail(from_email, [to_email], msg.as_string())
        server.quit()
        print(f"Email sent from {from_email} to {to_email}")
    except Exception as e:
        print(f"Failed to send email from {from_email} to {to_email}: {e}")

# Main loop
for sender in fromEmails:
    from_email = sender["email"]
    password = sender["password"]
    smtp_server = sender.get("smtpServer")
    smtp_port = sender.get("smtpPort", 465)
    max_messages = sender.get("maxMessages", len(messages))
    protocol = sender.get("protocol", "imaps")

    use_ssl = True if protocol.lower() == "imaps" else False

    selected_messages = random.sample(messages, min(max_messages, len(messages)))

    for idx, msg in enumerate(selected_messages, start=1):
        html_content = msg["message"]
        subject = f"Automated HTML Email {idx}"
        to_email = random.choice(toEmails)

        send_html_email(subject, html_content, from_email, password, to_email, smtp_server, smtp_port, use_ssl)
