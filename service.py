import os
import sys
import time
import signal
from typing import Sequence
from datetime import datetime, timedelta

# Ensure local imports work when running "python service.py"
sys.path.append(os.path.dirname(__file__))

from dotenv import load_dotenv
from sqlalchemy import select, update, delete
from sqlalchemy.exc import SQLAlchemyError

from db import session_scope  # your SessionLocal context manager
from models.models import EmailFetchRequest, SignatureResult  # your models
from imap_scraper import IMAPScraper  # your IMAP logic

# -------------------------
# Config
# -------------------------
load_dotenv()

POLL_SECONDS = int(os.getenv("POLL_SECONDS", "60"))               # how often to look for new jobs
MAX_JOBS_PER_CYCLE = int(os.getenv("MAX_JOBS_PER_CYCLE", "0"))    # 0 = no cap
RETENTION_DAYS = int(os.getenv("RESULT_RETENTION_DAYS", "3"))     # cleanup window for SignatureResult

# -------------------------
# Globals
# -------------------------
scraper = IMAPScraper()
_shutdown = False
_last_cleanup: datetime | None = None


def handle_sigterm(signum, frame):
    """Graceful shutdown on Ctrl+C / SIGTERM."""
    global _shutdown
    _shutdown = True
    print("[SYS] Received shutdown signal. Exiting gracefully...")


signal.signal(signal.SIGINT, handle_sigterm)
signal.signal(signal.SIGTERM, handle_sigterm)


# -------------------------
# Persistence helpers
# -------------------------
def pick_pending_jobs(limit: int | None = None) -> Sequence[EmailFetchRequest]:
    """
    Fetch pending jobs (status=0) ordered by id ascending.
    Detached from session for safe use outside with-block.
    """
    with session_scope() as s:
        stmt = select(EmailFetchRequest).where(EmailFetchRequest.status == 0).order_by(EmailFetchRequest.id.asc())
        if limit and limit > 0:
            stmt = stmt.limit(limit)
        jobs = s.execute(stmt).scalars().all()
        # detach
        for j in jobs:
            s.expunge(j)
        return jobs


def mark_running(job_id: int) -> bool:
    """
    Mark job as running (2) only if it is still pending (0).
    Returns True if we actually updated a row (race-safe).
    """
    with session_scope() as s:
        res = s.execute(
            update(EmailFetchRequest)
            .where(EmailFetchRequest.id == job_id, EmailFetchRequest.status == 0)
            .values(status=2)
        )
        return res.rowcount and res.rowcount > 0


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
        # If you keep last_error column in EmailFetchRequest, add it here.
        # Left out because your provided model doesn't include last_error.


def save_results(job_id: int, results: list[dict]):
    """
    Persist extracted signatures to SignatureResult, copying created_by
    from the parent EmailFetchRequest.
    """
    if not results:
        return

    with session_scope() as s:
        # Load the parent to grab created_by
        req = s.get(EmailFetchRequest, job_id)
        if not req:
            print(f"[WARN] EmailFetchRequest id={job_id} not found; skipping save.")
            return
        
        for r in results:
            row = SignatureResult(
                request_id=job_id,
                created_by=req.created_by,  # ✅ propagate created_by from parent
                message_uid=r.get("uid"),
                message_id=r.get("messageId"),
                mailbox=r.get("mailbox") or "INBOX",
                email=r.get("emailAddress"),
                company_name=r.get("companyName"),
                job_title=r.get("jobTitle"),
                phone=r.get("phoneNumber"),
                address=r.get("address"),
                website=r.get("website"),
                first_name=r.get("firstName"),
                last_name=r.get("lastName"),
                is_deleted=False
            )
            s.add(row)

def purge_deleted_results():
    print("[PURGE] Checking for messages to delete...")

    # Step 1: read everything we need first
    with session_scope() as s:
        rows = (
            s.execute(
                select(SignatureResult, EmailFetchRequest)
                .join(EmailFetchRequest, SignatureResult.request_id == EmailFetchRequest.id)
                .where(SignatureResult.is_deleted == True)  # noqa: E712
            )
            .all()
        )

        payload = []
        for sig, req in rows:
            payload.append({
                "sig_id": sig.id,
                "req_id": req.id,
                "mailbox": sig.mailbox or "INBOX",
                "host": req.imap_host,
                "port": req.imap_port or 993,
                "user": req.email,
                "password": req.password,
                "uid": sig.message_uid,
                "mid": sig.message_id,
            })

    if not payload:
        print("[PURGE] Nothing to delete.")
        return

    # Step 2: group and delete from IMAP
    deleted_sig_ids = []
    for item in payload:
        try:
            if item["uid"]:
                scraper.delete_by_uid(
                    host=item["host"], port=item["port"],
                    user=item["user"], password=item["password"],
                    mailbox=item["mailbox"], uids=[item["uid"]],
                )
            elif item["mid"]:
                scraper.delete_by_message_id(
                    host=item["host"], port=item["port"],
                    user=item["user"], password=item["password"],
                    mailbox=item["mailbox"], message_ids=[item["mid"]],
                )
            deleted_sig_ids.append(item["sig_id"])
        except Exception as e:
            print(f"[PURGE] Error deleting message {item['uid'] or item['mid']}: {e}")

    # Step 3: delete successfully purged rows from DB
    if deleted_sig_ids:
        with session_scope() as s:
            s.query(SignatureResult).filter(SignatureResult.id.in_(deleted_sig_ids)).delete(synchronize_session=False)
        print(f"[PURGE] Deleted {len(deleted_sig_ids)} rows from DB")




# -------------------------
# Job processing
# -------------------------
def process_job(job: EmailFetchRequest):
    """
    Run one job: mark running, fetch via IMAP, save results, mark done.
    Handles exceptions and marks failed.
    """
    print(f"[JOB {job.id}] Start — {job.email} @ {job.imap_host}:{job.imap_port} (max={job.max_messages})")

    # Attempt to acquire "lock" by transitioning 0 -> 2.
    if not mark_running(job.id):
        print(f"[JOB {job.id}] Skipped — not pending anymore (possibly picked by another worker).")
        return

    try:
        results = scraper.fetch_signatures(
            user_email=job.email,
            password=job.password,
            imap_host=job.imap_host,
            imap_port=job.imap_port or 993,
            max_messages=job.max_messages or 10,
        )
        save_results(job.id, results)
        mark_done(job.id)
        print(f"[JOB {job.id}] Done — saved {len(results)} signature(s).")
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
        print(f"[JOB {job.id}] FAILED — {err}")
        mark_failed(job.id, err)


# -------------------------
# Daily cleanup
# -------------------------
def cleanup_old_results():
    """
    Delete SignatureResult records older than RETENTION_DAYS based on created_date.
    """
    cutoff = datetime.utcnow() - timedelta(days=RETENTION_DAYS)
    print(f"[CLEANUP] Removing SignatureResult older than {RETENTION_DAYS} day(s) (cutoff: {cutoff:%Y-%m-%d %H:%M:%S} UTC)")

    with session_scope() as s:
        stmt = delete(SignatureResult).where(SignatureResult.created_date < cutoff)
        result = s.execute(stmt)
        deleted = result.rowcount or 0
        print(f"[CLEANUP] Deleted {deleted} record(s).")


# -------------------------
# Main loop
# -------------------------
def main():
    global _last_cleanup

    print("[SYS] MailScraper service started.")
    print(f"[SYS] Poll every {POLL_SECONDS}s | Max jobs/cycle: {MAX_JOBS_PER_CYCLE or '∞'} | Retention: {RETENTION_DAYS} day(s)")

    # First cleanup on startup
    _last_cleanup = datetime.utcnow()
    cleanup_old_results()

    while not _shutdown:
        try:
            jobs = pick_pending_jobs(limit=MAX_JOBS_PER_CYCLE if MAX_JOBS_PER_CYCLE > 0 else None)
            if jobs:
                for job in jobs:
                    if _shutdown:
                        break
                    process_job(job)

            # NEW: run purge pass every cycle (POLL_SECONDS defaults to 60)
            purge_deleted_results()

            # Daily cleanup (already in your code)
            now = datetime.utcnow()
            if (now - _last_cleanup).total_seconds() >= 86400:
                cleanup_old_results()
                _last_cleanup = now

            time.sleep(POLL_SECONDS)

        except SQLAlchemyError as db_err:
            print(f"[DB ERROR] {db_err}")
            time.sleep(POLL_SECONDS)
        except Exception as e:
            print(f"[ERROR] {type(e).__name__}: {e}")
            time.sleep(POLL_SECONDS)

    print("[SYS] MailScraper service stopped.")


if __name__ == "__main__":
    main()