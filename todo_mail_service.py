import mysql.connector
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timedelta
import time
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Database Configuration
DATABASE_URL = os.getenv("DATABASE_URL")

# Email Configuration
MAIL_HOST = os.getenv("MAIL_HOST")
MAIL_PORT = int(os.getenv("MAIL_PORT", 587))
MAIL_USERNAME = os.getenv("MAIL_USERNAME")
MAIL_PASSWORD = os.getenv("MAIL_PASSWORD")
MAIL_FROM = os.getenv("MAIL_FROM")
MAIL_FROM_NAME = os.getenv("MAIL_FROM_NAME")

def get_db_connection():
    """Parses DATABASE_URL and returns a mysql.connector connection."""
    # Example: mysql+mysqlconnector://root:@localhost/q4magic
    try:
        url = DATABASE_URL.replace("mysql+mysqlconnector://", "")
        if "@" in url:
            auth, host_port_db = url.split("@")
            user_pass = auth.split(":")
            user = user_pass[0]
            password = user_pass[1] if len(user_pass) > 1 else ""
            
            # Host/DB part
            if "/" in host_port_db:
                host, db = host_port_db.split("/")
            else:
                host = host_port_db
                db = ""
        else:
            # No auth part?
            user = "root"
            password = ""
            host = "localhost"
            db = url.split("/")[-1] if "/" in url else ""

        return mysql.connector.connect(
            host=host,
            user=user,
            password=password,
            database=db
        )
    except Exception as e:
        print(f"Error connecting to database: {e}")
        return None

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
        print(f"Email sent to {to_email} with subject: {subject}")
        return True
    except Exception as e:
        print(f"Failed to send email to {to_email}: {e}")
        return False

def sendTaskAssignedEmail(relatedTo, recipientName, recipientEmail, taskTitle, dueDate):
    subject = f"New Priority Assigned – {taskTitle}"
    dueDateText = dueDate if dueDate else "Not specified"
    body = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>New Priority Assigned</title>
<style>
body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
.footer {{ margin-top: 30px; font-size: 0.9em; color: #777; }}
</style>
</head>
<body>
<p>Hi {recipientName},</p>
<p>A new priority has been assigned to you:</p>
<ul>
  <li><strong>Related To:</strong> {relatedTo}</li>
  <li><strong>Action:</strong> {taskTitle}</li>
  <li><strong>Due Date:</strong> {dueDateText}</li>
</ul>
<p>Please review and take action inside 360Pipe.</p>
<p>Visibility drives progression — keep your deal momentum moving.</p>
<p class="footer">— 360Pipe</p>
</body>
</html>"""
    return send_email(recipientEmail, subject, body)

def sendDueSoonReminderEmail(relatedTo, recipientName, recipientEmail, taskTitle, dueDate):
    subject = f"Priority Due Soon – {taskTitle}"
    dueDateText = dueDate if dueDate else "Not specified"
    body = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>Priority Due Soon</title>
<style>
body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
.footer {{ margin-top: 30px; font-size: 0.9em; color: #777; }}
</style>
</head>
<body>
<p>Hi {recipientName if recipientName else 'User'},</p>
<p>Reminder: The following priority is due soon:</p>
<ul>
  <li><strong>Related To:</strong> {relatedTo if relatedTo else ''}</li>
  <li><strong>Action:</strong> {taskTitle if taskTitle else ''}</li>
  <li><strong>Due Date:</strong> {dueDateText}</li>
</ul>
<p>Please ensure next steps are scheduled and progressing.</p>
<p class="footer">— 360Pipe</p>
</body>
</html>"""
    return send_email(recipientEmail, subject, body)

def sendDueTodayReminderEmail(relatedTo, recipientName, recipientEmail, taskTitle):
    subject = f"Priority Due Today – {taskTitle}"
    body = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>Priority Due Today</title>
<style>
body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
.footer {{ margin-top: 30px; font-size: 0.9em; color: #777; }}
</style>
</head>
<body>
<p>Hi {recipientName if recipientName else 'User'},</p>
<p>The following priority is due today:</p>
<ul>
  <li><strong>Related To:</strong> {relatedTo if relatedTo else ''}</li>
  <li><strong>Action:</strong> {taskTitle if taskTitle else ''}</li>
</ul>
<p>Please complete or update the status in 360Pipe.</p>
<p class="footer">— 360Pipe</p>
</body>
</html>"""
    return send_email(recipientEmail, subject, body)

def sendPastDueReminderEmail(relatedTo, recipientName, recipientEmail, taskTitle, dueDate):
    subject = f"Priority Past Due – {taskTitle}"
    dueDateText = dueDate if dueDate else "Not specified"
    body = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>Priority Past Due</title>
<style>
body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
.footer {{ margin-top: 30px; font-size: 0.9em; color: #777; }}
</style>
</head>
<body>
<p>Hi {recipientName if recipientName else 'User'},</p>
<p>The following priority is now past due:</p>
<ul>
  <li><strong>Related To:</strong> {relatedTo if relatedTo else ''}</li>
  <li><strong>Action:</strong> {taskTitle if taskTitle else ''}</li>
  <li><strong>Original Due Date:</strong> {dueDateText}</li>
</ul>
<p>Please review and update the status in 360Pipe.</p>
<p>Past-due priorities are visible in your team dashboard.</p>
<p class="footer">— 360Pipe</p>
</body>
</html>"""
    return send_email(recipientEmail, subject, body)

def sendTaskReminder():
    """Main logic: Fetches todos, checks due dates, and sends reminders to assignees."""
    conn = get_db_connection()
    if not conn:
        return

    try:
        cursor = conn.cursor(dictionary=True)
        
        # 1. Fetch all todos from todos table
        cursor.execute("SELECT todo_id, related_to, task, due_date FROM todo WHERE is_deleted = 0")
        todos = cursor.fetchall()

        today = datetime.now().date()

        for todo in todos:
            due_date = todo['due_date']
            if not due_date:
                continue
            
            # due_date might be a datetime object or a string depending on mysql-connector behavior
            if isinstance(due_date, datetime):
                due_date_ptr = due_date.date()
                formatted_due_date = due_date.strftime("%Y-%m-%d")
            elif isinstance(due_date, str):
                try:
                    due_date_ptr = datetime.strptime(due_date, "%Y-%m-%d").date()
                    formatted_due_date = due_date
                except:
                    # try another format if needed
                    continue
            else:
                due_date_ptr = due_date # assuming it's already a date object
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
                # Fetch assignees for this todo
                cursor.execute("""
                    SELECT c.username, c.email_address 
                    FROM todo_assignees ta
                    JOIN customers c ON ta.cus_id_assignee = c.cus_id
                    WHERE ta.todo_id = %s
                """, (todo['todo_id'],))
                assignees = cursor.fetchall()

                for assignee in assignees:
                    name = assignee['username']
                    email = assignee['email_address']
                    
                    if not email:
                        continue

                    if reminder_type == "today":
                        sendDueTodayReminderEmail(todo['related_to'], name, email, todo['task'])
                    elif reminder_type == "soon":
                        sendDueSoonReminderEmail(todo['related_to'], name, email, todo['task'], formatted_due_date)
                    elif reminder_type == "past":
                        sendPastDueReminderEmail(todo['related_to'], name, email, todo['task'], formatted_due_date)

    except Exception as e:
        print(f"Error in sendTaskReminder: {e}")
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    print("Todo Mail Service started...")
    while True:
        print(f"Running task reminder at {datetime.now()}")
        sendTaskReminder()
        print("Task reminder completed. Sleeping for 24 hours...")
        # 24 hours = 86400 seconds
        time.sleep(86400)
