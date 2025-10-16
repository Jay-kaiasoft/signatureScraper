# service.py
"""
Standalone MailScraper service.
- Connects to MySQL
- Every POLL_SECONDS, looks for EmailFetchRequest with status=0
- Marks a picked job to status=2 (running), processes it, stores SignatureResult rows
- On success -> status=1, on failure -> status=-1 (optional but useful)
- Continues forever until interrupted (Ctrl+C)

Run:  python service.py
"""

import os
import time
import signal
import sys
from dotenv import load_dotenv
from typing import Sequence

from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError

from db import engine, session_scope
from models.models import Base, EmailFetchRequest, SignatureResult
from imap_scraper import IMAPScraper

load_dotenv()

POLL_SECONDS = int(os.getenv("POLL_SECONDS", "60"))
MAX_JOBS_PER_CYCLE = int(os.getenv("MAX_JOBS_PER_CYCLE", "0"))  # 0 = no cap

scraper = IMAPScraper()
_shutdown = False

def handle_sigterm(signum, frame):
    global _shutdown
    _shutdown = True
    print("Received shutdown signal. Exiting gracefully...")

signal.signal(signal.SIGINT, handle_sigterm)
signal.signal(signal.SIGTERM, handle_sigterm)

# def ensure_schema():
#     """
#     Create tables if they do not exist.
#     """
#     Base.metadata.create_all(bind=engine)

def pick_pending_jobs(limit: int | None = None) -> Sequence[EmailFetchRequest]:
    """
    Fetch pending jobs (status=0). Optionally limit.
    """
    with session_scope() as s:
        stmt = select(EmailFetchRequest).where(EmailFetchRequest.status == 0).order_by(EmailFetchRequest.id.asc())
        if limit and limit > 0:
            stmt = stmt.limit(limit)
        jobs = s.execute(stmt).scalars().all()
        # detach to allow use after session closes
        for j in jobs:
            s.expunge(j)
        return jobs

def mark_running(job_id: int):
    with session_scope() as s:
        s.execute(
            update(EmailFetchRequest)
            .where(EmailFetchRequest.id == job_id, EmailFetchRequest.status == 0)
            .values(status=2)
        )

def mark_done(job_id: int):
    with session_scope() as s:
        s.execute(
            update(EmailFetchRequest)
            .where(EmailFetchRequest.id == job_id)
            .values(status=1)
        )

def mark_failed(job_id: int, error_msg: str):
    with session_scope() as s:
        s.execute(
            update(EmailFetchRequest)
            .where(EmailFetchRequest.id == job_id)
            .values(status=-1)
        )

def save_results(job_id: int, results: list[dict]):
    """
    Persist extracted signatures to SignatureResult table.
    """
    if not results:
        return
    with session_scope() as s:
        # Optionally: clear previous results for this job (if you rerun)
        # s.query(SignatureResult).filter(SignatureResult.request_id == job_id).delete()

        for r in results:
            row = SignatureResult(
                request_id = job_id,
                email= r.get("emailAddress"),
                company_name = r.get("companyName"),
                job_title    = r.get("jobTitle"),
                phone = r.get("phoneNumber"),
                address     = r.get("address"),
                website     = r.get("website"),
            )
            s.add(row)

def process_job(job: EmailFetchRequest):
    """
    Run a single job: mark running, fetch via IMAP, save results, mark done.
    """
    print(f"[JOB {job.id}] Starting: {job.email} @ {job.imap_host}:{job.imap_port}, max={job.max_messages}")
    try:
        mark_running(job.id)
        results = scraper.fetch_signatures(
            user_email=job.email,
            password=job.password,
            imap_host=job.imap_host,
            imap_port=job.imap_port or 993,
            max_messages=job.max_messages or 10,
        )
        save_results(job.id, results)
        mark_done(job.id)
        print(f"[JOB {job.id}] Completed. {len(results)} signature(s) saved.")
    except Exception as e:
        error_text = f"{type(e).__name__}: {e}"
        print(f"[JOB {job.id}] FAILED -> {error_text}")
        mark_failed(job.id, error_text)

def main():
    print("Starting MailScraper service…")
    # ensure_schema()
    print("Database schema ensured. Polling for jobs.")

    while not _shutdown:
        try:
            jobs = pick_pending_jobs(limit=MAX_JOBS_PER_CYCLE if MAX_JOBS_PER_CYCLE > 0 else None)
            if not jobs:
                # No work; sleep
                time.sleep(POLL_SECONDS)
                continue

            for job in jobs:
                if _shutdown:
                    break
                process_job(job)

            # After processing batch, sleep
            time.sleep(POLL_SECONDS)

        except SQLAlchemyError as db_err:
            print(f"[DB ERROR] {db_err}")
            time.sleep(POLL_SECONDS)
        except Exception as e:
            print(f"[ERROR] {type(e).__name__}: {e}")
            time.sleep(POLL_SECONDS)

    print("MailScraper service stopped.")

if __name__ == "__main__":
    main()
