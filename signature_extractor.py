# signature_extractor.py
from __future__ import annotations

import re
from typing import List, Optional, Tuple, Iterable
from email.utils import parseaddr

import html2text
from bs4 import BeautifulSoup
import tldextract  # pip install tldextract


LEGAL_SUFFIXES = (
    "Inc", "Inc.", "LLC", "Ltd", "Ltd.", "Corp", "Corporation", "Company", "Co.", "GmbH",
    "Pvt", "Private Limited", "LLP", "PLC", "S.A.", "SAS", "BV", "AG", "Oy", "AB"
)

COPYRIGHT_WORDS = (
    "copyright", "©", "all rights reserved", "rights reserved", "®", "™"
)

UNSUB_WORDS = (
    "unsubscribe", "opt-out", "optout", "privacy policy", "terms of service", "click here"
)

TRACKING_HINTS = (
    "utm_", "trk", "track", "click", "email", "unsubscribe", "mandrillapp", "sendgrid",
    "mailchimp", "list-manage", "t.sidekick", "link.track", "protector", "r20.rs6.net",
    "emltrk", "sfmc", "postmarkapp", "sparkpost", "amazonses"
)

CURRENCY_HINTS = ("rs.", "rs", "₹", "$", "usd", "inr", "eur")


class ImprovedSignatureExtractor:
    def __init__(self):
        self.job_titles = [
            "CEO","CTO","CFO","COO","CMO","CIO","CDO","Manager","Director","Engineer",
            "Developer","Analyst","Designer","Lead","Head","Specialist","Officer",
            "President","Vice President","VP","Partner","Consultant","Architect",
            "Coordinator","Administrator","Executive","Founder","Co-Founder","Owner",
            "Principal","Associate","Assistant","Supervisor","Team Lead","Product Manager",
            "Project Manager","Sales Manager","Marketing Manager","Senior","Junior","Staff"
        ]
        self.email_pattern  = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        self.phone_pattern  = r'(?:\+?\d{1,3}[\s.-]?)?\(?\d{2,4}\)?[\s.-]?\d{3,4}[\s.-]?\d{3,4}(?:\s*(?:ext|x|extension)\s*\d{1,5})?'
        self.website_pattern= r'(?:https?://)?(?:www\.)?[a-zA-Z0-9][-a-zA-Z0-9]*\.[a-zA-Z]{2,}(?:/[^\s]*)?'

        self.metadata_patterns = [
            r'^From:\s*.+$', r'^Sent:\s*.+$', r'^To:\s*.+$', r'^Subject:\s*.+$',
            r'^Date:\s*.+$', r'^Cc:\s*.+$', r'^Bcc:\s*.+$',
            r'^\*\*From:\*\*.+$', r'^\*\*Sent:\*\*.+$', r'^\*\*To:\*\*.+$', r'^\*\*Subject:\*\*.+$',
        ]
        self.signature_separators = [
            r'^[\s_*=-]{2,}$', r'^--\s*$', r'^Thanks?[,!]?\s*$', r'^Best[,!]?\s*$',
            r'^Regards?[,!]?\s*$', r'^Sincerely[,!]?\s*$', r'^Cheers?[,!]?\s*$',
            r'^Warm regards?[,!]?\s*$', r'^Kind regards?[,!]?\s*$', r'^Best regards?[,!]?\s*$',
        ]

        # generic tokens we strip from domain-derived brand names
        self._generic_brand_tokens = {
            "mail","email","mailer","mx","smtp","noreply","no-reply","notify","notification",
            "newsletter","news","updates","support","help","helpdesk","service","services",
            "account","accounts","communication","gateway","secure","auth","login","signin",
            "web","app","apps","cloud","online","corp","company"
        }

    _MINI_ROLE_WORDS = {
        "support","help","hello","contact","team","sales","marketing","info",
        "noreply","no-reply","donotreply","newsletter","alerts","updates",
        "admin","hr","jobs","career","careers","billing","accounts"
    }

    def _cap(self, s: str) -> str:
        s = s.strip()
        return s if not s else s[0].upper() + s[1:].lower()

    def _looks_like_person(self, disp: str) -> bool:
        # two tokens, mostly letters, no obvious role words
        toks = [t for t in disp.strip().split() if any(c.isalpha() for c in t)]
        if len(toks) < 2: 
            return False
        low = disp.lower()
        if any(w in low for w in self._MINI_ROLE_WORDS):
            return False
        return True

    def _split_local_simple(self, local: str) -> list[str]:
        base = local.split('+', 1)[0]
        parts = re.split(r'[._\-]+', base)
        if len(parts) == 1 and re.search(r'[a-z][A-Z]', parts[0]):  # camelCase → "John Doe"
            parts = re.sub(r'([a-z])([A-Z])', r'\1 \2', parts[0]).split()
        parts = [re.sub(r'^\d+|\d+$', '', p) for p in parts]        # trim edge digits
        parts = [p for p in parts if re.search(r'[A-Za-z]', p)]     # keep alphabetic-ish
        return parts

    def _is_role_local(self, local: str) -> bool:
        base = local.split('+', 1)[0].lower()
        bits = re.split(r'[._\-]+', base)
        return any(b in self._MINI_ROLE_WORDS for b in bits)

    def _name_from_email_simple(self, email_addr: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
        if not email_addr or '@' not in email_addr:
            return None, None, None
        local, _ = email_addr.split('@', 1)
        if self._is_role_local(local):
            return None, None, None

        parts = self._split_local_simple(local)
        if not parts:
            return None, None, None

        if len(parts) == 1:
            first = self._cap(parts[0])
            last  = None
        else:
            first = self._cap(parts[0])
            last  = self._cap(parts[-1])

        # SAFE full name (no str+None)
        full = " ".join([p for p in [first, last] if p]) or None
        return first, last, full


    def _simple_name_from_header_or_email(self, sender_header: Optional[str], fallback_email: Optional[str]):
        # 1) Try display name
        if sender_header:
            disp, addr = parseaddr(sender_header)
            disp = disp.strip(' "\'|,;()[]')
            if self._looks_like_person(disp):
                toks = [t for t in disp.split() if any(c.isalpha() for c in t)]
                if toks:
                    first = self._cap(toks[0])
                    last  = self._cap(toks[-1]) if len(toks) > 1 else None
                    full  = " ".join([p for p in [first, last] if p]) or None
                    return first, last, full
            if not fallback_email and addr:
                fallback_email = addr

        # 2) Fallback to email local-part
        return self._name_from_email_simple(fallback_email)



    # ---------- helpers ----------
    def _text_has(self, s: str, words: Iterable[str]) -> bool:
        sl = s.lower()
        return any(w in sl for w in words)

    def _clean_token(self, w: str) -> str:
        return w.strip(".,;·*()[]{}<>|\"'")

    def _valid_domain(self, token: str) -> Optional[str]:
        """
        Validate and normalize a domain-like token using tldextract.
        Returns the registered_domain if valid, else None.
        """
        token = self._clean_token(token)
        if not token or "@" in token:
            return None
        if self._text_has(token, CURRENCY_HINTS):
            return None
        if any(c.isdigit() for c in token) and not any(ch.isalpha() for ch in token):
            return None

        # add scheme for parsing if missing
        if not token.startswith(("http://", "https://")):
            candidate = f"http://{token}"
        else:
            candidate = token

        ext = tldextract.extract(candidate)
        if not ext.suffix:  # no TLD
            return None

        registered = ".".join(part for part in [ext.domain, ext.suffix] if part)
        if not registered:
            return None

        full_host = ".".join(part for part in [ext.subdomain, ext.domain, ext.suffix] if part)
        if self._text_has(full_host, TRACKING_HINTS):
            return None

        return registered.lower()

    def _brand_from_registered_domain(self, registered_domain: Optional[str]) -> Optional[str]:
        """
        Convert a registered domain like 'microsoft.com' or 'adobe.co.uk' to a human brand.
        Heuristics only — no hard-coded brand lists.
        """
        if not registered_domain:
            return None
        rd = registered_domain.lower()

        # Take the registrable label (leftmost part before the first dot)
        label = rd.split(".", 1)[0]  # 'microsoft' in microsoft.com
        # strip digits and generic noise from label edges
        label = re.sub(r'\d+', '', label)

        # split on hyphen/underscore; drop generic tokens if multiple parts
        parts = [p for p in re.split(r"[-_]", label) if p]
        if len(parts) > 1:
            parts = [p for p in parts if p not in self._generic_brand_tokens]

        # if nothing remains, fall back to original label
        if not parts:
            parts = [label] if label else []

        # TitleCase join (TradingView style for 'trading-view')
        brand = "".join(p.capitalize() for p in parts)
        return brand or None

    def _prefer_website(self, candidates: List[str], sender_domain: Optional[str]) -> Optional[str]:
        """
        Choose the best website:
        - prefer sender_domain
        - else the most concise (shortest) registered domain
        """
        if not candidates:
            return None
        norm = [c.lower() for c in candidates]
        if sender_domain and sender_domain.lower() in norm:
            return sender_domain.lower()
        norm = sorted(set(norm), key=lambda x: (len(x), x))
        return norm[0] if norm else None

    # ---------- HTML + text cleaning ----------
    def _extract_links_and_text(self, raw_html_or_text: str) -> Tuple[List[str], List[str]]:
        """
        Returns (valid_domains_from_links, cleaned_text_lines).
        Parses links BEFORE converting to text so we don't lose anchor hrefs.
        """
        links_domains: List[str] = []

        soup = BeautifulSoup(raw_html_or_text, 'html.parser')

        # collect hrefs
        for a in soup.find_all("a", href=True):
            href = a["href"].split("?")[0]
            dom = self._valid_domain(href)
            if dom:
                links_domains.append(dom)

        # remove noisy tags for text
        for tag in soup(["script", "style", "meta", "link", "head"]):
            tag.decompose()

        text = soup.get_text(separator="\n")
        if not text.strip():
            # fallback to html2text only if soup yielded nothing
            h = html2text.HTML2Text()
            h.ignore_links = True
            h.ignore_images = True
            h.ignore_emphasis = False
            text = h.handle(raw_html_or_text)

        # remove unsubscribe/copyright/price lines early + very long boilerplate
        lines = []
        for line in (ln.strip() for ln in text.splitlines()):
            if not line:
                continue
            if len(line) > 200:
                continue
            lcl = line.lower()
            if any(x in lcl for x in UNSUB_WORDS) or any(cw in lcl for cw in COPYRIGHT_WORDS):
                continue
            # drop obvious price-like lines ("Rs.62999*", "$15000", etc.)
            if self._text_has(lcl, CURRENCY_HINTS) and re.search(r'\d', lcl):
                continue
            lines.append(line)

        # drop metadata
        cleaned = []
        for line in lines:
            if any(re.match(p, line, re.IGNORECASE) for p in self.metadata_patterns):
                continue
            cleaned.append(line)

        # dedup consecutive
        dedup, prev = [], None
        for line in cleaned:
            if line != prev:
                dedup.append(line)
                prev = line

        return links_domains, dedup

    # ---------- detection ----------
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

    # ---------- components ----------
    def extract_emails(self, text: str) -> list[str]:
        emails = re.findall(self.email_pattern, text, re.IGNORECASE)
        return list(dict.fromkeys([e for e in emails if not re.search(r'(example\.com|test\.com|localhost)', e, re.IGNORECASE)]))

    # add these helpers anywhere inside the class
    def _normalize_phone(self, s: str) -> tuple[str, str | None]:
        """
        Normalize to digits-only (keep leading + if present).
        Returns (main_number, ext) where ext may be None.
        """
        # extract extension
        ext_match = re.search(r'(?:ext|x|extension)\s*(\d{1,5})\b', s, re.IGNORECASE)
        ext = ext_match.group(1) if ext_match else None

        # strip everything except digits and leading +
        s = s.strip()
        has_plus = s.strip().startswith('+')
        digits = re.sub(r'[^\d]', '', s)
        if has_plus:
            norm = f'+{digits}'
        else:
            norm = digits
        return norm, ext

    def _looks_like_tracking_id(self, original: str, normalized: str) -> bool:
        """
        Heuristic to reject IDs:
        - very long uninterrupted digits with no + and no separators
        - or > 12 digits without plus (too long for many local formats)
        """
        # no separators in original?
        sep_in_original = bool(re.search(r'[()\s.\-]', original))
        # long uninterrupted digits without plus?
        if not original.strip().startswith('+') and not sep_in_original and len(normalized) >= 12:
            return True
        return False

    # replace your current extract_phones with this
    def extract_phones(self, text: str) -> list[str]:
        """
        Stricter phone extraction:
        - Context-aware (phone/mobile/tel/etc.) OR numbers with typical separators
        - E.164 validation for '+' numbers: +[1-9] followed by 6–14 digits (total 7–15)
        - For numbers without '+': allow 7–12 digits; reject long uninterrupted blobs (likely IDs)
        - Handles extensions (ext/x/extension 123)
        """

        # 1) find candidates with context (preferred)
        context_words = r'(?:phone|mobile|cell|tel|telephone|call|contact|office|work|fax)'
        # capture a number-like chunk with separators; require at least 7 digits overall
        number_chunk = r'(\+?\d[\d\s().-]{5,24}\d)'
        context_pattern = re.compile(
            rf'(?:{context_words}\s*[:\-]?\s*{number_chunk})|(?:{number_chunk}\s*(?:{context_words}))',
            re.IGNORECASE
        )

        # 2) fallback: standalone number-like chunks with separators or leading +
        loose_pattern = re.compile(r'(\+?\d[\d\s().-]{5,24}\d)')

        candidates: list[tuple[str, str]] = []  # (original_chunk, source) source = 'context' | 'loose'

        for m in context_pattern.finditer(text):
            # the regex has two capture groups; pick the one that matched
            chunk = m.group(1) or m.group(2)
            if chunk:
                candidates.append((chunk, 'context'))

        if not candidates:
            for m in loose_pattern.finditer(text):
                chunk = m.group(1)
                if chunk:
                    candidates.append((chunk, 'loose'))

        results: list[str] = []
        seen: set[str] = set()

        for original, source in candidates:
            norm, ext = self._normalize_phone(original)

            # basic sanity
            if not norm:
                continue

            # reject obvious tracking-like blobs
            if self._looks_like_tracking_id(original, norm):
                continue

            # E.164 strict if has '+'
            if norm.startswith('+'):
                # must be + followed by 7–15 digits total
                if not re.fullmatch(r'\+[1-9]\d{6,14}', norm):
                    continue
            else:
                # no plus: keep only 7–12 digits (avoid very long IDs)
                if not re.fullmatch(r'\d{7,12}', norm):
                    continue

            # avoid price-like fragments (₹/$ with digits nearby already filtered upstream,
            # but double-check around the original chunk)
            window = 6
            start = max(0, text.find(original) - window)
            end = min(len(text), start + len(original) + 2 * window)
            around = text[start:end].lower()
            if self._text_has(around, CURRENCY_HINTS):
                # price context, likely not a phone
                continue

            # final normalization (append ext with x if present)
            final = norm if not ext else f"{norm} x{ext}"

            if final not in seen:
                seen.add(final)
                results.append(final)

        return results

    def extract_websites(self, raw_html_or_text: str, lines: List[str], sender_domain: Optional[str]) -> Optional[str]:
        """
        Extract a reliable website:
        - Parse <a href> links, validate domains
        - Scan text tokens for domains and validate
        - Prefer sender_domain; otherwise pick a clean, short registered domain
        """
        links_domains, _ = self._extract_links_and_text(raw_html_or_text)
        text_domains: List[str] = []

        for line in lines:
            for word in line.split():
                token = self._clean_token(word)
                if "." not in token or "@" in token:
                    continue
                dom = self._valid_domain(token)
                if dom:
                    text_domains.append(dom)

        candidates = list(dict.fromkeys(links_domains + text_domains))
        return self._prefer_website(candidates, sender_domain)

    def extract_job_title(self, lines: List[str]) -> Optional[str]:
        """
        Extracts just the job-title phrase from signature lines.
        Examples it captures:
        - "IT Engineer"
        - "Project Coordinator"
        - "Account Manager"
        - "Service Ops Director"
        - "Senior Product Manager"
        - "VP" / "Vice President"
        - "CEO", "CTO", ...
        It avoids returning the rest of the sentence around the title.
        """
        # Core "head" nouns for titles (we'll allow 0–3 capitalized words before these)
        head_nouns = (
            "Manager|Director|Engineer|Coordinator|Architect|Analyst|Designer|Officer|"
            "Executive|Developer|Consultant|Specialist|Administrator|Supervisor|Owner|"
            "Founder|President"
        )

        # Seniority / modifiers we may see before the phrase
        seniority = r"(?:Senior|Sr\.|Junior|Jr\.|Lead|Principal|Head|Chief|Assistant|Associate)"

        # Up to 3 capitalized tokens before the head noun (e.g., "IT", "Account", "Service Ops")
        pre_modifiers = r"(?:(?:[A-Z][A-Za-z/&+.-]{1,20}|[A-Z]{2,6})\s+){0,3}"

        # Pattern 1: generic titles like "Service Ops Director", "Account Manager", "Senior Product Manager"
        generic_title_pat = re.compile(
            rf"\b(?:{seniority}\s+)?{pre_modifiers}(?:{head_nouns})\b",
            re.IGNORECASE,
        )

        # Pattern 2: C-suite & short forms that stand on their own
        csuite_pat = re.compile(
            r"\b(?:CEO|CTO|CFO|COO|CMO|CIO|CDO|CPO|CSO|CHRO|CISO|CRO|VP|Vice President)\b",
            re.IGNORECASE,
        )

        # Helper to trim punctuation/extra spaces
        def _clean_phrase(s: str) -> str:
            s = re.sub(r"\s{2,}", " ", s).strip()
            return s.strip(",.;:—- ")

        # Scan a few likely signature lines
        for line in lines[:12]:
            # Skip obvious non-title lines
            if (
                re.search(self.email_pattern, line, re.IGNORECASE)
                or re.search(self.phone_pattern, line)
                or re.search(self.website_pattern, line, re.IGNORECASE)
                or len(line) < 2
            ):
                continue

            # Try C-suite first (simple, precise)
            m2 = csuite_pat.search(line)
            if m2:
                return _clean_phrase(m2.group(0).title() if m2.group(0).isupper() else m2.group(0))

            # Then generic titles with optional modifiers
            # Find the *shortest* reasonable match in case multiple exist on a long line
            matches = list(generic_title_pat.finditer(line))
            if matches:
                # Prefer the match that ends closest to punctuation/comma (often the “title” chunk)
                # then fallback to the shortest span.
                best = None
                best_score = (10**9, 10**9)  # (distance_to_punct, span_len)
                for m in matches:
                    span = m.span()
                    after = line[span[1]:]
                    punct_pos = re.search(r"[,.;:|–—\-]", after)
                    dist = punct_pos.start() if punct_pos else len(after)
                    span_len = span[1] - span[0]
                    score = (dist, span_len)
                    if score < best_score:
                        best_score = score
                        best = m
                if best:
                    phrase = _clean_phrase(best.group(0))
                    # Normalize capitalization (keep ALLCAPS acronyms, title-case words)
                    parts = []
                    for tok in phrase.split():
                        if tok.isupper() and len(tok) <= 6:
                            parts.append(tok)          # keep acronyms like IT, VP
                        else:
                            parts.append(tok[0].upper() + tok[1:])
                    phrase = " ".join(parts)
                    # guard against returning very long chunks
                    if 2 <= len(phrase) <= 60:
                        return phrase

        return None


    def _extract_company_from_line(self, line: str) -> Optional[str]:
        """
        Capture a company phrase ending with a legal suffix, while trimming trailing boilerplate.
        Example: "Samsung Electronics Co. Ltd. All rights reserved" -> "Samsung Electronics Co. Ltd."
        """
        if self._text_has(line, COPYRIGHT_WORDS) or self._text_has(line, CURRENCY_HINTS):
            return None
        if len(line) > 120 or len(line) < 3:
            return None

        # Legal-suffix anchored phrase
        pattern = r'([A-Z][\w&.,\- ]{1,100}?\b(?:' + "|".join(re.escape(s) for s in LEGAL_SUFFIXES) + r')\.?)\b'
        m = re.search(pattern, line)
        if m:
            company = m.group(1)
            company = re.sub(r'\s{2,}', ' ', company).strip(" ,.-")
            return company

        # Fallback: short capitalized phrase that looks like a brand
        words = [w for w in re.split(r'\s+', line.strip()) if w]
        if 1 <= len(words) <= 6 and all(any(ch.isalpha() for ch in w) for w in words):
            if not self._text_has(line, ("dear", "thanks", "regards", "hello", "team", "support")):
                return line.strip(" .,|-")

        return None

    def extract_company_name(self, lines: List[str], sender_domain: Optional[str]) -> Optional[str]:
        """
        Strategy:
        1) If we have a sender registered domain -> derive brand dynamically (no hard-coded map).
        2) Otherwise, try legal-suffix phrases from the signature lines.
        3) As a last resort, pick a short capitalized phrase that doesn't look like
           an email/URL/copyright/price line.
        """
        # 1) Prefer brand from sender domain (dynamic)
        brand = self._brand_from_registered_domain(sender_domain)
        if brand:
            return brand

        # 2) Scan lines for a legal-suffix company phrase
        for line in lines[:12]:
            if self._text_has(line, ("dear", "hello", "hi,", "regards", "thanks")):
                continue
            if self._looks_like_email_or_url(line):
                continue
            cand = self._extract_company_from_line(line)
            if cand:
                return cand

        # 3) Fallback: short capitalized phrase
        for line in lines[:12]:
            if self._looks_like_email_or_url(line):
                continue
            l = line.strip()
            if self._text_has(l, ("team", "support", "helpdesk", "noreply", "no-reply")):
                continue
            if self._text_has(l, ("copyright", "©", "all rights reserved")):
                continue
            if self._text_has(l.lower(), CURRENCY_HINTS) and re.search(r"\d", l):
                continue

            words = [w for w in re.split(r"\s+", l) if w]
            if 1 <= len(words) <= 4 and all(any(ch.isalpha() for ch in w) for w in words):
                return " ".join(w[0].upper() + w[1:] if w else w for w in words)

        return None

    def _looks_like_email_or_url(self, s: str) -> bool:
        """Filter out lines that are likely an email address or URL."""
        if "@" in s:
            return True
        if re.search(r"https?://|\bwww\.", s, re.IGNORECASE):
            return True
        # bare domain token
        tokens = re.findall(r"[A-Za-z0-9.-]+\.[A-Za-z]{2,}", s)
        return bool(tokens)

    def extract_address(self, lines: List[str]) -> Optional[str]:
        address_lines = []
        address_keywords = [
            r'\b(Street|St|Road|Rd|Avenue|Ave|Boulevard|Blvd|Lane|Ln|Drive|Dr)\b',
            r'\b(Suite|Ste|Floor|Fl|Room|Unit|Building|Tower|Center|Centre)\b',
            r'\b(City|State|Province|Country|Zip|Postal|Code)\b',
            r'\d{3,6}',
        ]
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

    # ---------- main ----------
    def extract_signature(self, raw_body: str, sender_header: str | None = None) -> dict:
        # Parse sender email + normalize to registered domain
        sender_email, sender_name = None, None
        sender_domain = None
        if sender_header:
            sender_name, sender_email = parseaddr(sender_header)
            if sender_email and "@" in sender_email:
                raw_dom = sender_email.split("@", 1)[1].lower()
                ext = tldextract.extract(raw_dom)
                if ext.suffix:
                    sender_domain = ".".join(p for p in [ext.domain, ext.suffix] if p)

        # Extract links & cleaned text lines
        _, lines = self._extract_links_and_text(raw_body)

        # Focus on the likely signature block
        sig_start = self.find_signature_start(lines)
        sig_lines = lines[sig_start:]
        sig_text = '\n'.join(sig_lines)

        # Components
        emails = self.extract_emails(sig_text)
        phones = self.extract_phones(sig_text)
        website = self.extract_websites(raw_body, sig_lines, sender_domain)
        company_name = self.extract_company_name(sig_lines, sender_domain)
        job_title = self.extract_job_title(sig_lines)
        address = self.extract_address(sig_lines)

    # add inside ImprovedSignatureExtractor (near your other helpers)
        def _compose_full(self, first: Optional[str], last: Optional[str]) -> Optional[str]:
            if first and last:
                return f"{first} {last}"
            return first or last  # could be None if both are None

        # Sender email fallback
        email_addr = sender_email if sender_email else (emails[0] if emails else None)

        # SIMPLE name extraction
        # first_name, last_name, full_name = self._simple_name_from_header_or_email(sender_header, email_addr)
        first_name, last_name, full_name = self._simple_name_from_header_or_email(sender_header, email_addr)

        return {
            "firstName": first_name,
            "lastName": last_name,
            "emailAddress": email_addr,
            "companyName": company_name,
            "jobTitle": job_title,
            "phoneNumber": phones[0] if phones else None,
            "address": address,
            "website": website
        }

    # ---------- legacy compatibility ----------
    def clean_text(self, raw_text: str) -> List[str]:
        """
        Legacy alias for old code paths. Returns cleaned lines like the old implementation.
        """
        _, lines = self._extract_links_and_text(raw_text)
        return lines