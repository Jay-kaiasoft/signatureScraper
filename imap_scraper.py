# imap_scraper.py
"""
IMAP fetcher that logs in, pulls the latest messages, and extracts signatures.
Returns a list of dicts (subject + signature fields).
"""

import imaplib
import email
from email.header import decode_header
from typing import List
from signature_extractor import ImprovedSignatureExtractor

class IMAPScraper:
    def __init__(self):
        self.extractor = ImprovedSignatureExtractor()

    def _decode_subject(self, msg) -> str | None:
        if not msg["Subject"]:
            return None
        subject_parts = decode_header(msg["Subject"])
        pieces = []
        for part, encoding in subject_parts:
            if isinstance(part, bytes):
                pieces.append(part.decode(encoding or "utf-8", errors="ignore"))
            else:
                pieces.append(str(part))
        return "".join(pieces) if pieces else None

    def fetch_signatures(
        self,
        user_email: str,
        password: str,
        imap_host: str,
        imap_port: int = 993,
        max_messages: int = 10,
    ) -> List[dict]:
        """
        Connect to IMAP, fetch recent messages, extract signatures.
        Returns: list of dicts with keys: subject, emailAddress, companyName, jobTitle,
                 phoneNumber, address, website
        """
        mail = imaplib.IMAP4_SSL(imap_host, imap_port)
        try:
            mail.login(user_email, password)
        except imaplib.IMAP4.error as e:
            raise RuntimeError(
                f"Authentication failed for {user_email}. "
                f"Check host/port and use App Password if 2FA is enabled. ({str(e)})"
            )

        try:
            mail.select("inbox")
            status, data = mail.search(None, "ALL")
            if status != "OK":
                raise RuntimeError("Failed to fetch emails")

            email_ids = data[0].split()[-max_messages:]
            results = []

            for e_id in reversed(email_ids):
                status, msg_data = mail.fetch(e_id, "(RFC822)")
                if status != "OK":
                    continue
                raw_email = msg_data[0][1]
                msg = email.message_from_bytes(raw_email)

                subject = self._decode_subject(msg)

                # Extract body (text/plain and text/html parts)
                body = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        content_type = part.get_content_type()
                        if content_type in ["text/plain", "text/html"]:
                            payload = part.get_payload(decode=True)
                            if payload:
                                body += payload.decode(errors="ignore")
                else:
                    payload = msg.get_payload(decode=True)
                    if payload:
                        body = payload.decode(errors="ignore")

                signature = self.extractor.extract_signature(body, sender_header=msg.get("From"))

                # Fallback email from body if not found in header
                if not signature.get("emailAddress"):
                    body_emails = self.extractor.extract_emails(body)
                    if body_emails:
                        signature["emailAddress"] = body_emails[0]

                signature["subject"] = subject
                results.append(signature)

            return results
        finally:
            try:
                mail.logout()
            except Exception:
                pass