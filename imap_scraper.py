import imaplib
from signature_extractor import ImprovedSignatureExtractor
from email.header import decode_header, make_header
from typing import List, Dict, Optional, Tuple,Iterable
import email


def _decode_header_value(value: Optional[str]) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value))).strip()
    except Exception:
        return value.strip()

def _walk_parts_for_bodies(msg: email.message.Message) -> Tuple[Optional[str], Optional[str]]:
    """
    Returns (html_body, text_body) as strings (or None). We don't set \Seen.
    """
    html_body = None
    text_body = None

    if msg.is_multipart():
        for part in msg.walk():
            ctype = (part.get_content_type() or "").lower()
            if part.get_content_maintype() == "multipart":
                continue
            if part.get("Content-Disposition", "").lower().startswith("attachment"):
                continue

            try:
                payload = part.get_payload(decode=True)
            except Exception:
                payload = None

            if not payload:
                continue

            charset = (part.get_content_charset() or "utf-8").strip("'\"").lower()
            try:
                text = payload.decode(charset, errors="replace")
            except Exception:
                # fallback if the declared charset is bogus
                text = payload.decode("utf-8", errors="replace")

            if ctype == "text/html" and html_body is None:
                html_body = text
            elif ctype == "text/plain" and text_body is None:
                text_body = text
    else:
        # single-part message
        payload = msg.get_payload(decode=True) or b""
        charset = (msg.get_content_charset() or "utf-8").strip("'\"").lower()
        try:
            text = payload.decode(charset, errors="replace")
        except Exception:
            text = payload.decode("utf-8", errors="replace")

        ctype = (msg.get_content_type() or "").lower()
        if ctype == "text/html":
            html_body = text
        else:
            text_body = text

    return html_body, text_body

def _html_to_text(html: str) -> str:
    # tiny inline converter to avoid extra deps; replace with html2text if you prefer
    try:
        # lazy import to keep module import cheap
        from bs4 import BeautifulSoup  # type: ignore
        soup = BeautifulSoup(html, "html.parser")
        # drop scripts/styles
        for tag in soup(["script", "style", "meta", "link", "head"]):
            tag.decompose()
        return soup.get_text(separator="\n")
    except Exception:
        # worst case, strip tags crudely
        import re
        return re.sub(r"<[^>]+>", " ", html)
    
def _naive_signature_extract(body_text: str) -> Dict[str, Optional[str]]:
    """
    Minimal fallback extractor so this function is self-contained.
    Replace with your signature_extractor module if available.
    """
    import re
    email_pat = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
    phone_pat = re.compile(r"(?:\+?\d{1,3}[\s.-]?)?(?:\(?\d{2,4}\)?[\s.-]?)?\d{3,4}[\s.-]?\d{3,4}")
    website_pat = re.compile(r"(?:https?://)?(?:www\.)?[a-zA-Z0-9][-a-zA-Z0-9]*\.[a-zA-Z]{2,}(?:/[^\s]*)?")

    email_addr = next(iter(email_pat.findall(body_text)), None)
    phone = next(iter(phone_pat.findall(body_text)), None)
    website = next(iter(website_pat.findall(body_text)), None)

    return {
        "emailAddress": email_addr,
        "companyName": None,
        "jobTitle": None,
        "phoneNumber": phone,
        "address": None,
        "website": website,
        "firstName": None,
        "lastName": None,
    }


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
        mailbox: str = "INBOX",
        search: str = "ALL",             # e.g. 'UNSEEN', 'ALL', '(SINCE 01-Oct-2025)'
        max_messages: int = 200,
        extractor=None,                  # optional override; otherwise uses self.extractor
    ) -> List[Dict]:
        """
        Returns list of dicts:
          { uid, messageId, mailbox,
            emailAddress, companyName, jobTitle, phoneNumber, address, website,
            firstName, lastName }
        """
        # login with the host/port you passed from the DB job
        M = self._login(imap_host, imap_port, user_email, password)
        try:
            typ, _ = M.select(mailbox, readonly=True)
            if typ != "OK":
                return []

            # use UID so we can delete later by UID
            typ, data = M.uid("SEARCH", None, search)
            if typ != "OK" or not data or not data[0]:
                return []

            uids = data[0].split()
            if max_messages and max_messages > 0:
                uids = uids[-max_messages:]

            out: List[Dict] = []
            for uid in uids:
                typ, msg_data = M.uid("FETCH", uid, "(BODY.PEEK[] RFC822.HEADER)")
                if typ != "OK" or not msg_data or not isinstance(msg_data[0], tuple):
                    continue

                raw = msg_data[0][1]
                if not raw:
                    continue

                msg = email.message_from_bytes(raw)

                from_hdr   = _decode_header_value(msg.get("From"))
                subject    = _decode_header_value(msg.get("Subject"))
                message_id = (msg.get("Message-ID") or msg.get("Message-Id") or msg.get("Message-id") or "").strip() or None

                html_body, text_body = _walk_parts_for_bodies(msg)
                body_text = text_body or (_html_to_text(html_body) if html_body else "")

                # prefer the improved extractor; fall back to naive
                parsed: Dict[str, Optional[str]] = {}
                try:
                    use_extractor = extractor or self.extractor
                    if hasattr(use_extractor, "extract_signature"):
                        # our ImprovedSignatureExtractor API
                        parsed = use_extractor.extract_signature(
                            raw_body=html_body or body_text,
                            sender_header=from_hdr or None,
                        ) or {}
                    elif hasattr(use_extractor, "extract_from_email"):
                        # legacy/custom API
                        from_name, from_addr = email.utils.parseaddr(from_hdr)
                        parsed = use_extractor.extract_from_email(
                            html=html_body,
                            text=body_text,
                            from_name=from_name or None,
                            from_addr=from_addr or None,
                            subject=subject or None,
                        ) or {}
                except Exception:
                    parsed = {}

                if not parsed:
                    parsed = _naive_signature_extract(body_text)

                out.append({
                    "uid": int(uid),
                    "messageId": message_id,
                    "mailbox": mailbox,
                    **parsed,
                })

            return out
        finally:
            try:
                M.close()
            except Exception:
                pass
            M.logout()

    def _login(self, host: str, port: int, user: str, password: str) -> imaplib.IMAP4_SSL:
        M = imaplib.IMAP4_SSL(host, port)
        M.login(user, password)
        return M

    def delete_by_uid(self, host: str, port: int, user: str, password: str, mailbox: str, uids: Iterable[int]) -> int:
        if not uids:
            return 0
        M = self._login(host, port, user, password)
        try:
            M.select(mailbox or "INBOX")
            # mark each UID as \Deleted
            for uid in uids:
                M.uid("STORE", str(uid), "+FLAGS", r"(\Deleted)")
            # expunge once per mailbox batch
            M.expunge()
            return len(list(uids))
        finally:
            try: M.close()
            except: pass
            M.logout()

    def delete_by_message_id(self, host: str, port: int, user: str, password: str, mailbox: str, message_ids: Iterable[str]) -> int:
        if not message_ids:
            return 0
        M = self._login(host, port, user, password)
        deleted = 0
        try:
            M.select(mailbox or "INBOX")
            for mid in message_ids:
                # Search by exact Message-ID (quotes required)
                typ, data = M.search(None, '(HEADER Message-ID "{}")'.format(mid))
                if typ == "OK" and data and data[0]:
                    for msg_id in data[0].split():
                        M.store(msg_id, "+FLAGS", r"(\Deleted)")
                        deleted += 1
            M.expunge()
            return deleted
        finally:
            try: M.close()
            except: pass
            M.logout()