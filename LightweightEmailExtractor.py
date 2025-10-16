from email.mime import text
from email.utils import parseaddr
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional
import imaplib
import email
from email.header import decode_header
import html2text
import re
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from fastapi.middleware.cors import CORSMiddleware


# -------------------------------
# Pydantic model for API input
# -------------------------------
class EmailFetchRequest(BaseModel):
    email: str
    password: str
    protocol: str = Field(default="imaps", description="IMAP or POP3 protocol")
    imap_host: str = Field(..., description="IMAP server hostname, e.g. imap.gmail.com or outlook.office365.com")
    imap_port: int = Field(default=993, description="IMAP server port, typically 993 for SSL or 143 for STARTTLS")
    maxMessages: int = Field(default=10, description="Maximum number of messages to fetch")


# -------------------------------
# Improved Signature Extractor
# -------------------------------
class ImprovedSignatureExtractor:
    def __init__(self):
        self.job_titles = [
            "CEO", "CTO", "CFO", "COO", "CMO", "CIO", "CDO",
            "Manager", "Director", "Engineer", "Developer", "Analyst",
            "Designer", "Lead", "Head", "Specialist", "Officer",
            "President", "Vice President", "VP", "Partner", "Consultant",
            "Architect", "Coordinator", "Administrator", "Executive",
            "Founder", "Co-Founder", "Owner", "Principal", "Associate",
            "Assistant", "Supervisor", "Team Lead", "Product Manager",
            "Project Manager", "Sales Manager", "Marketing Manager",
            "Senior", "Junior", "Staff"
        ]

        self.email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        self.phone_pattern = r'(?:\+?\d{1,3}[\s.-]?)?\(?\d{2,4}\)?[\s.-]?\d{3,4}[\s.-]?\d{3,4}(?:\s*(?:ext|x|extension)\s*\d{1,5})?'
        self.website_pattern = r'(?:https?://)?(?:www\.)?[a-zA-Z0-9][-a-zA-Z0-9]*\.[a-zA-Z]{2,}(?:/[^\s]*)?'

        self.metadata_patterns = [
            r'^From:\s*.+$',
            r'^Sent:\s*.+$',
            r'^To:\s*.+$',
            r'^Subject:\s*.+$',
            r'^Date:\s*.+$',
            r'^Cc:\s*.+$',
            r'^Bcc:\s*.+$',
            r'^\*\*From:\*\*.+$',
            r'^\*\*Sent:\*\*.+$',
            r'^\*\*To:\*\*.+$',
            r'^\*\*Subject:\*\*.+$',
        ]

        self.signature_separators = [
            r'^[\s_*=-]{2,}$',
            r'^--\s*$',
            r'^Thanks?[,!]?\s*$',
            r'^Best[,!]?\s*$',
            r'^Regards?[,!]?\s*$',
            r'^Sincerely[,!]?\s*$',
            r'^Cheers?[,!]?\s*$',
            r'^Warm regards?[,!]?\s*$',
            r'^Kind regards?[,!]?\s*$',
            r'^Best regards?[,!]?\s*$',
        ]

    # ------------------- Cleaning HTML / Text -------------------
    def clean_html(self, raw_text: str) -> str:
        soup = BeautifulSoup(raw_text, 'html.parser')
        for script in soup(["script", "style", "meta", "link", "head"]):
            script.decompose()
        text = soup.get_text(separator='\n')
        if not text.strip():
            h = html2text.HTML2Text()
            h.ignore_links = True
            h.ignore_images = True
            h.ignore_emphasis = False
            text = h.handle(raw_text)
        return text

    def remove_metadata_lines(self, lines: List[str]) -> List[str]:
        cleaned = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if any(re.match(p, line, re.IGNORECASE) for p in self.metadata_patterns):
                continue
            cleaned.append(line)
        return cleaned

    def clean_text(self, raw_text: str) -> List[str]:
        text = self.clean_html(raw_text)
        text = re.sub(r'(unsubscribe|click here|opt[- ]out|privacy policy|terms of service)[^\n]*', '', text, flags=re.IGNORECASE)
        text = re.sub(r'https?://[^\s]*(?:unsubscribe|optout|remove)[^\s]*', '', text, flags=re.IGNORECASE)
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        lines = self.remove_metadata_lines(lines)
        # remove consecutive duplicates
        cleaned_lines = []
        prev_line = None
        for line in lines:
            if line != prev_line:
                cleaned_lines.append(line)
                prev_line = line
        return cleaned_lines

    # ------------------- Signature Detection -------------------
    def find_signature_start(self, lines: List[str]) -> int:
        for i in range(len(lines) - 1, max(0, len(lines) - 30), -1):
            line = lines[i].strip()
            if any(re.match(p, line, re.IGNORECASE) for p in self.signature_separators):
                return i
        for i in range(len(lines) - 1, max(0, len(lines) - 25), -1):
            if re.search(r'\b(Best|Regards|Sincerely|Thank you|Thanks|Cheers|Warm regards|Kind regards|Best regards)\b', lines[i], re.IGNORECASE):
                return i
        for i in range(len(lines) - 1, max(0, len(lines) - 20), -1):
            if re.search(self.email_pattern, lines[i]) or re.search(self.phone_pattern, lines[i]):
                return max(0, i - 5)
        return max(0, len(lines) - 15)

    # ------------------- Component Extractors -------------------
    def extract_emails(self, text: str) -> List[str]:
        emails = re.findall(self.email_pattern, text, re.IGNORECASE)
        return list(dict.fromkeys([e for e in emails if not re.search(r'(example\.com|test\.com|localhost)', e, re.IGNORECASE)]))

    def extract_phones(self, text: str) -> List[str]:
        phones = re.findall(self.phone_pattern, text)
        cleaned = []
        for phone in phones:
            clean = re.sub(r'[^\d+\-\s]', '', phone).strip()
            if len(re.findall(r'\d', clean)) >= 7:
                cleaned.append(clean)
        return list(dict.fromkeys(cleaned))

    def extract_website_from_text(self, text):
        lines = text.splitlines()
        results = []
        for line in reversed(lines):
            words = line.split()
            for word in reversed(words):
                word = word.strip(".,;·")
                if '.' in word and '@' not in word:
                    results.append(word)
        return results



    def extract_job_title(self, lines: List[str]) -> Optional[str]:
        for line in lines[:10]:
            line_lower = line.lower()
            if re.search(self.email_pattern, line) or re.search(self.phone_pattern, line) or re.search(self.website_pattern, line):
                continue
            if len(line) > 80:
                continue
            for title in self.job_titles:
                if re.search(r'\b' + re.escape(title.lower()) + r'\b', line_lower):
                    cleaned = re.sub(r'[|\[\]{}]', '', line).strip()
                    if cleaned:
                        return cleaned
        return None
  
    def extract_company_name(self, lines: List[str]) -> Optional[str]:
        company_indicators = [
            r'\b(Inc|LLC|Ltd|Corp|Corporation|Company|Co\.|GmbH|Pvt|Private Limited|LLP)\b',
            r'\b(Technologies|Solutions|Services|Systems|Software|Consulting|Group)\b',
        ]
        for line in lines[:10]:
            if re.search(self.email_pattern, line) or re.search(self.phone_pattern, line):
                continue
            for indicator in company_indicators:
                if re.search(indicator, line, re.IGNORECASE):
                    cleaned = re.sub(r'[|\[\]{}]', '', line).strip()
                    if 3 <= len(cleaned) <= 80:
                        return cleaned
        return None

    def extract_address(self, lines: List[str]) -> Optional[str]:
        address_lines = []
        address_keywords = [
            r'\b(Street|St|Road|Rd|Avenue|Ave|Boulevard|Blvd|Lane|Ln|Drive|Dr)\b',
            r'\b(Suite|Ste|Floor|Fl|Room|Unit|Building|Tower|Center|Centre)\b',
            r'\b(City|State|Province|Country|Zip|Postal|Code)\b',
            r'\d{3,6}',
        ]
        # location_names = [
        #     r'\b(New York|Los Angeles|Chicago|Houston|Phoenix|Philadelphia|San Antonio|San Diego|Dallas|San Jose)\b',
        #     r'\b(California|Texas|Florida|New York|Pennsylvania|Illinois|Ohio|Georgia|North Carolina|Michigan|Gujarat|Maharashtra|Karnataka|Delhi)\b',
        #     r'\b(USA|United States|UK|United Kingdom|Canada|Australia|India|Germany|France|China|Japan)\b',
        #     r'\b(CA|TX|FL|NY|PA|IL|OH|GA|NC|MI)\b',
        # ]
        for line in lines:
            line_cleaned = line.strip()
            if re.search(self.email_pattern, line_cleaned) or re.search(self.phone_pattern, line_cleaned) or re.search(self.website_pattern, line_cleaned):
                continue
            if len(line_cleaned) < 5 or len(line_cleaned) > 120:
                continue
            if any(re.search(kw, line_cleaned, re.IGNORECASE) for kw in address_keywords):
                cleaned = re.sub(r'[|\[\]{}]', '', line_cleaned).strip()
                cleaned = re.sub(r'\s+', ' ', cleaned)
                if cleaned and cleaned not in address_lines:
                    address_lines.append(cleaned)
        return ', '.join(address_lines[:3]) if address_lines else None

    # ------------------- Main Extraction -------------------
    def extract_signature(self, raw_text: str, sender_header: str = None) -> dict:
        lines = self.clean_text(raw_text)
        sig_start = self.find_signature_start(lines)
        sig_lines = lines[sig_start:]
        sig_text = '\n'.join(sig_lines)

        emails = self.extract_emails(sig_text)
        phones = self.extract_phones(sig_text)
        websites = self.extract_website_from_text(sig_text)
        job_title = self.extract_job_title(sig_lines)
        company_name = self.extract_company_name(sig_lines)
        address = self.extract_address(sig_lines)

        # Extract sender email from header if provided
        sender_email = None
        sender_name = None
        if sender_header:
            sender_name, sender_email = parseaddr(sender_header)

        return {
            "emailAddress": sender_email if sender_email else (emails[0] if emails else None),
            "companyName": company_name,
            "jobTitle": job_title,
            "phoneNumber": phones[0] if phones else None,
            "address": address,
            "website": websites[0] if websites else None
        }


# -------------------------------
# FastAPI app
# -------------------------------
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
extractor = ImprovedSignatureExtractor()

@app.post("/fetch-signatures")
async def fetch_signatures(request: EmailFetchRequest):
    try:
        imap_host = request.imap_host
        imap_port = request.imap_port

        # Connect to IMAP
        mail = imaplib.IMAP4_SSL(imap_host, imap_port)
        try:
            mail.login(request.email, request.password)
        except imaplib.IMAP4.error as e:
            raise HTTPException(
                status_code=401,
                detail=f"Authentication failed for {request.email}. "
                    f"Check host/port and use App Password if 2FA is enabled. ({str(e)})"
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
        # Select inbox
        mail.select("inbox")

        # Get email IDs
        status, data = mail.search(None, "ALL")
        if status != "OK":
            raise HTTPException(status_code=500, detail="Failed to fetch emails")

        email_ids = data[0].split()[-request.max_messages:]
        results = []

        for e_id in reversed(email_ids):
            status, msg_data = mail.fetch(e_id, "(RFC822)")
            if status != "OK":
                continue

            raw_email = msg_data[0][1]
            msg = email.message_from_bytes(raw_email)

            # Decode subject
            subject = None
            if msg["Subject"]:
                subject_parts = decode_header(msg["Subject"])
                subject = "".join(
                    part.decode(encoding if encoding else "utf-8", errors="ignore") 
                    if isinstance(part, bytes) else str(part)
                    for part, encoding in subject_parts
                )

            # Extract body
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

            # Extract signature
            signature = extractor.extract_signature(body, sender_header=msg.get("From"))

            # Fallback: if sender email not found in header, try body
            if not signature.get("emailAddress"):
                body_emails = extractor.extract_emails(body)
                signature["emailAddress"] = body_emails[0] if body_emails else None

            signature["subject"] = subject
            results.append(signature)


        mail.logout()
        return {
            "imapHost": imap_host,
            "signatures": results
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/ping")
async def ping():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

# uvicorn LightweightEmailExtractor:app --reload
# {
#     "email": "slms.gov@outlook.com",
#     "password": "qnvnawdqikbldkzj",
#     "protocol": "imaps",
#     "maxMessages": 10
# }

# {
#   "email": "webzoidsolution@gmail.com",
#   "password": "fdee tasv dsop rzwr",
#   "protocol": "imaps",
#   "maxMessages": 5
# }

# {
#   "email": "sweetheart3329@gmail.com",
#   "accountPassword": "tysonrai",
#   "password": "bett ucvd unep jime",
#   "protocol": "imaps",
#   "maxMessages": 5
# }

# {
#   "email": "dhruvdobariya04@yahoo.com",
#   "accountPassword": "01Dhruv007!",
#   "password": "sfcynsioclascrbl",
#   "protocol": "imaps",
#   "maxMessages": 10
# }

# {
#     "imap_host": "theaisaasnews.com",
#     "email": "info@theaisaasnews.com",
#     "password": "01eMatrix007!",
#     "imap_port": 993,
#     "protocol": "imaps",
#     "maxMessages": 50
# }

# {
    #  "email": "support@salesandmarketing.ai",
    #  "password": "!01Sup@SamAi@2025!",
    #  "protocol": "imaps",
    #  "imap_host": "imap-mail.outlook.com",
    #  "imap_port": 143,
    #  "maxMessages": 5
#  }


# {
#     "detail": "Authentication failed for jay@kaiasoft.com. Use App Password if 2FA is enabled. (b'LOGIN failed.')"
# }
