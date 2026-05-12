import logger_config
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from contextlib import contextmanager
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timedelta
import time
import os
from dotenv import load_dotenv
import logging
logger = logging.getLogger(__name__)

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

MAIL_HOST = os.getenv("MAIL_HOST")
MAIL_PORT = int(os.getenv("MAIL_PORT", 587))
MAIL_USERNAME = os.getenv("MAIL_USERNAME")
MAIL_PASSWORD = os.getenv("MAIL_PASSWORD")
MAIL_FROM = os.getenv("MAIL_FROM")
MAIL_FROM_NAME = os.getenv("MAIL_FROM_NAME")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set in .env")

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    echo=False
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False
)

@contextmanager
def session_scope():
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        logger.exception("DB session rolled back")
        raise
    finally:
        session.close()

def send_email(to_email, subject, body):
    """Sends an HTML email using SMTP."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{MAIL_FROM_NAME} <{MAIL_FROM}>"
    msg["To"] = to_email
    msg.attach(MIMEText(body, "html"))

    try:
        server = smtplib.SMTP(MAIL_HOST, MAIL_PORT)
        server.starttls()
        server.login(MAIL_USERNAME, MAIL_PASSWORD)
        server.sendmail(MAIL_FROM, [to_email], msg.as_string())
        server.quit()
        logger.info(f"Email sent to {to_email} with subject: {subject}")
        return True
    except Exception as e:
        logger.info(f"Failed to send email to {to_email}: {e}")
        return False

def sendTaskAssignedEmail(relatedTo, recipientName, recipientEmail, taskTitle, dueDate):
    subject = f"New Priority Assigned – {taskTitle}"
    dueDateText = dueDate if dueDate else "Not specified"
    
    # Get current year for footer
    current_year = datetime.now().year
    
    body = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>New Priority Assigned</title>
<style>
body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; margin: 0; padding: 0; }}
.container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
.header {{ text-align: center; padding: 20px 0; border-bottom: 2px solid #eee; }}
.logo {{ max-width: 180px; height: auto; }}
.content {{ padding: 20px 0; }}
.footer {{ margin-top: 30px; padding-top: 20px; border-top: 1px solid #eee; font-size: 0.9em; color: #777; text-align: center; }}
</style>
</head>
<body>
<div class="container">
<div class="header">
<img src="https://devwebapp.360pipe.com/images/logo/360Pipe_logo.png" alt="360Pipe Logo" class="logo">
</div>
<div class="content">
<p>Hi {recipientName},</p>
<p>A new priority has been assigned to you:</p>
<ul>
  <li><strong>Related To:</strong> {relatedTo}</li>
  <li><strong>Action:</strong> {taskTitle}</li>
  <li><strong>Due Date:</strong> {dueDateText}</li>
</ul>
<p>Please review and take action inside <a href="https://devwebapp.360pipe.com/dashboard/todos">360Pipe</a>.</p>
<p>Visibility drives progression — keep your deal momentum moving.</p>
</div>
<div class="footer">
<p>&copy; {current_year} 360Pipe. All rights reserved.</p>
</div>
</div>
</body>
</html>"""
    return send_email(recipientEmail, subject, body)

def sendDueSoonReminderEmail(relatedTo, recipientName, recipientEmail, taskTitle, dueDate):
    subject = f"Priority Due Soon – {taskTitle}"
    dueDateText = dueDate if dueDate else "Not specified"
    current_year = datetime.now().year
    
    body = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>Priority Due Soon</title>
<style>
body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; margin: 0; padding: 0; }}
.container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
.header {{ text-align: center; padding: 20px 0; border-bottom: 2px solid #eee; }}
.logo {{ max-width: 180px; height: auto; }}
.content {{ padding: 20px 0; }}
.footer {{ margin-top: 30px; padding-top: 20px; border-top: 1px solid #eee; font-size: 0.9em; color: #777; text-align: center; }}
</style>
</head>
<body>
<div class="container">
<div class="header">
<img src="https://devwebapp.360pipe.com/images/logo/360Pipe_logo.png" alt="360Pipe Logo" class="logo">
</div>
<div class="content">
<p>Hi {recipientName if recipientName else recipientEmail},</p>
<p>Reminder: The following priority is due soon:</p>
<ul>
  <li><strong>Related To:</strong> {relatedTo if relatedTo else ''}</li>
  <li><strong>Action:</strong> {taskTitle if taskTitle else ''}</li>
  <li><strong>Due Date:</strong> {dueDateText}</li>
</ul>
<p>Please complete or update the status in  <a href="https://devwebapp.360pipe.com/dashboard/todos">360Pipe</a>.</p>
</div>
<div class="footer">
<p>&copy; {current_year} 360Pipe. All rights reserved.</p>
</div>
</div>
</body>
</html>"""
    return send_email(recipientEmail, subject, body)

def sendDueTodayReminderEmail(relatedTo, recipientName, recipientEmail, taskTitle):
    subject = f"Priority Due Today – {taskTitle}"
    current_year = datetime.now().year
    
    body = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>Priority Due Today</title>
<style>
body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; margin: 0; padding: 0; }}
.container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
.header {{ text-align: center; padding: 20px 0; border-bottom: 2px solid #eee; }}
.logo {{ max-width: 180px; height: auto; }}
.content {{ padding: 20px 0; }}
.footer {{ margin-top: 30px; padding-top: 20px; border-top: 1px solid #eee; font-size: 0.9em; color: #777; text-align: center; }}
</style>
</head>
<body>
<div class="container">
<div class="header">
<img src="https://devwebapp.360pipe.com/images/logo/360Pipe_logo.png" alt="360Pipe Logo" class="logo">
</div>
<div class="content">
<p>Hi {recipientName if recipientName else recipientEmail},</p>
<p>The following priority is due today:</p>
<ul>
  <li><strong>Related To:</strong> {relatedTo if relatedTo else ''}</li>
  <li><strong>Action:</strong> {taskTitle if taskTitle else ''}</li>
</ul>
<p>Please complete or update the status in  <a href="https://devwebapp.360pipe.com/dashboard/todos">360Pipe</a>.</p>
</div>
<div class="footer">
<p>&copy; {current_year} 360Pipe. All rights reserved.</p>
</div>
</div>
</body>
</html>"""
    return send_email(recipientEmail, subject, body)

def sendPastDueReminderEmail(relatedTo, recipientName, recipientEmail, taskTitle, dueDate):
    subject = f"Priority Past Due – {taskTitle}"
    dueDateText = dueDate if dueDate else "Not specified"
    current_year = datetime.now().year
    
    body = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>Priority Past Due</title>
<style>
body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; margin: 0; padding: 0; }}
.container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
.header {{ text-align: center; padding: 20px 0; border-bottom: 2px solid #eee; }}
.logo {{ max-width: 180px; height: auto; }}
.content {{ padding: 20px 0; }}
.footer {{ margin-top: 30px; padding-top: 20px; border-top: 1px solid #eee; font-size: 0.9em; color: #777; text-align: center; }}
</style>
</head>
<body>
<div class="container">
<div class="header">
<img src="https://devwebapp.360pipe.com/images/logo/360Pipe_logo.png" alt="360Pipe Logo" class="logo">
</div>
<div class="content">
<p>Hi {recipientName if recipientName else recipientEmail},</p>
<p>The following priority is now past due:</p>
<ul>
  <li><strong>Related To:</strong> {relatedTo if relatedTo else ''}</li>
  <li><strong>Action:</strong> {taskTitle if taskTitle else ''}</li>
  <li><strong>Original Due Date:</strong> {dueDateText}</li>
</ul>
<p>Please review and update the status in 360Pipe.</p>
<p>Past-due priorities are visible in your team dashboard.</p>
</div>
<div class="footer">
<p>&copy; {current_year} 360Pipe. All rights reserved.</p>
</div>
</div>
</body>
</html>"""
    return send_email(recipientEmail, subject, body)

def sendTaskReminder():
    """Fetch todos and send reminder emails."""

    try:
        with session_scope() as session:

            todos_query = text("""
                SELECT
                    todo_id,
                    related_to,
                    task,
                    due_date
                FROM todo
                WHERE is_deleted = 0
            """)

            todos = session.execute(todos_query).mappings().all()

            today = datetime.now().date()

            for todo in todos:

                due_date = todo["due_date"]

                if not due_date:
                    continue

                if isinstance(due_date, datetime):
                    due_date_ptr = due_date.date()
                    formatted_due_date = due_date.strftime("%Y-%m-%d")

                elif isinstance(due_date, str):
                    try:
                        due_date_ptr = datetime.strptime(
                            due_date,
                            "%Y-%m-%d"
                        ).date()

                        formatted_due_date = due_date

                    except Exception:
                        continue

                else:
                    due_date_ptr = due_date
                    formatted_due_date = str(due_date)

                days_diff = (due_date_ptr - today).days

                reminder_type = None

                if days_diff == 0:
                    reminder_type = "today"

                elif days_diff == 2:
                    reminder_type = "soon"

                elif days_diff == -1:
                    reminder_type = "past"

                if reminder_type:

                    assignees_query = text("""
                        SELECT
                            c.username,
                            c.email_address
                        FROM todo_assignees ta
                        JOIN customers c
                            ON ta.cus_id_assignee = c.cus_id
                        WHERE ta.todo_id = :todo_id
                    """)

                    assignees = session.execute(
                        assignees_query,
                        {"todo_id": todo["todo_id"]}
                    ).mappings().all()

                    for assignee in assignees:

                        name = assignee["username"]
                        email = assignee["email_address"]

                        if not email:
                            continue

                        if reminder_type == "today":

                            sendDueTodayReminderEmail(
                                todo["related_to"],
                                name,
                                email,
                                todo["task"]
                            )

                        elif reminder_type == "soon":

                            sendDueSoonReminderEmail(
                                todo["related_to"],
                                name,
                                email,
                                todo["task"],
                                formatted_due_date
                            )

                        elif reminder_type == "past":

                            sendPastDueReminderEmail(
                                todo["related_to"],
                                name,
                                email,
                                todo["task"],
                                formatted_due_date
                            )

    except Exception as e:
        logger.info(f"Error in sendTaskReminder: {e}")
if __name__ == "__main__":
    logger.info("Todo Mail Service started...")
    while True:
        logger.info(f"Running task reminder at {datetime.now()}")
        sendTaskReminder()
        logger.info("Task reminder completed. Sleeping for 24 hours...")
        time.sleep(86400)