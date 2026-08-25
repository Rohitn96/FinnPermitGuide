"""
MigriGuide — Stage 1: Data Collection v2

Key improvements:
  1. HTML tables → pipe-formatted text: income/fee/threshold tables are now readable
  2. Automatic sublink discovery: crawls within each domain beyond the seed list
  3. Added: suomi.fi/en, enterfinland.fi
  4. Domain-specific path filters (English-only, skip nav/admin/auth pages)
  5. Per-domain page caps to prevent runaway crawling (~900 pages total max)

Sources covered:
  migri.fi, infofinland.fi, kela.fi, dvv.fi, vero.fi, suomi.fi,
  enterfinland.fi, workinfinland.eu, ihhelsinki.fi, poliisi.fi,
  tulli.fi, tyosuojelu.fi, tyomarkkinatori.fi, te-palvelut.fi
"""

import json
import logging
import re
import time
from collections import deque
from pathlib import Path
from urllib.parse import urljoin, urlparse

import fitz  # PyMuPDF
import requests
from bs4 import BeautifulSoup

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

# ── Paths ──────────────────────────────────────────────────────────────────────
BASE_DIR  = Path(__file__).resolve().parent.parent
RAW_DIR   = BASE_DIR / "data" / "raw"
PDF_DIR   = RAW_DIR / "pdfs"
PAGES_OUT = RAW_DIR / "migri_pages.json"
PDF_OUT   = RAW_DIR / "pdf_content.json"

RAW_DIR.mkdir(parents=True, exist_ok=True)
PDF_DIR.mkdir(parents=True, exist_ok=True)

# ── Request config ─────────────────────────────────────────────────────────────
REQUEST_DELAY = 1.5   # seconds between requests — respectful crawling
TIMEOUT       = 25

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; FinnPermitGuide-Bot/2.0; "
        "educational/non-commercial; +https://finnpermit.com)"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Tags to remove entirely before text extraction
NOISE_TAGS = [
    "nav", "footer", "header", "script", "style", "noscript",
    "aside", "form", "button", "iframe", "svg", "figure",
    "breadcrumb", "cookie-consent", "cookie-bar",
]

# ── Domain configurations ──────────────────────────────────────────────────────
# lang_prefix : required path prefix for English pages (None = no restriction)
# max_pages   : hard cap on pages scraped from this domain
# skip        : any URL containing these substrings is rejected
#
# Order matters: more-specific domains (subdomains) must come before their parents.
DOMAIN_CONFIGS = {
    "toimistot.te-palvelut.fi": {
        "lang_prefix": None,
        "max_pages": 15,
        "skip": ["/fi/", "/sv/"],
    },
    "migri.fi": {
        "lang_prefix": "/en/",
        "max_pages": 250,
        "skip": ["/fi/", "/sv/", "/ar/", "/so/", "/ru/", "/sitemap", "?lang=", "/search"],
    },
    "infofinland.fi": {
        "lang_prefix": "/en/",
        "max_pages": 130,
        "skip": ["/fi/", "/sv/", "/ar/", "/so/", "/ru/", "/search", "?lang="],
    },
    "kela.fi": {
        "lang_prefix": None,
        "max_pages": 90,
        "skip": ["/fi/", "/sv/", "/ar/", "/ru/", "/web/fi", "/web/sv",
                 "/web/ar", "?lang=fi", "?lang=sv"],
    },
    "dvv.fi": {
        "lang_prefix": "/en/",
        "max_pages": 60,
        "skip": ["/fi/", "/sv/", "/ar/"],
    },
    "vero.fi": {
        "lang_prefix": "/en/",
        "max_pages": 70,
        "skip": ["/fi/", "/sv/", "/ar/", "?lang=", "/search"],
    },
    "suomi.fi": {
        "lang_prefix": None,
        "max_pages": 20,
        "skip": ["/fi/", "/sv/", "/ar/", "/ru/", "/so/", "/search", "?lang=",
                 "/palvelut/", "/lomakkeet/"],
    },
    "enterfinland.fi": {
        "lang_prefix": None,
        "max_pages": 25,
        "skip": ["/fi/", "/sv/", "login", "logout", "register",
                 "dashboard", "my-applications", "status", "pay"],
    },
    "workinfinland.eu": {
        "lang_prefix": "/en/",
        "max_pages": 50,
        "skip": ["/fi/", "/sv/"],
    },
    "ihhelsinki.fi": {
        "lang_prefix": None,
        "max_pages": 30,
        "skip": ["/fi/", "/sv/", "appointment", "booking", "varaa"],
    },
    "poliisi.fi": {
        "lang_prefix": "/en/",
        "max_pages": 50,
        "skip": ["/fi/", "/sv/", "/ru/", "/ar/", "/so/"],
    },
    "tulli.fi": {
        "lang_prefix": "/en/",
        "max_pages": 40,
        "skip": ["/fi/", "/sv/"],
    },
    "tyosuojelu.fi": {
        "lang_prefix": "/en/",
        "max_pages": 50,
        "skip": ["/fi/", "/sv/"],
    },
    "tyomarkkinatori.fi": {
        "lang_prefix": "/en/",
        "max_pages": 40,
        "skip": ["/fi/", "/sv/"],
    },
    "te-palvelut.fi": {
        "lang_prefix": "/en/",
        "max_pages": 25,
        "skip": ["/fi/", "/sv/"],
    },
}

# URL patterns that are always rejected regardless of domain
GLOBAL_SKIP = [
    "#", "mailto:", "tel:", "javascript:", "data:",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".zip",
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".css", ".js", ".xml",
    "/logout", "/login", "/register", "/admin", "/404", "/403",
    "?print=", "?format=pdf", "?download=", "?share=",
    "/feed/", "/rss/", "/atom/",
]

# ── Seed URLs ──────────────────────────────────────────────────────────────────
# Starting points for each domain. The crawler will discover sublinks from these.

SEED_URLS = [

    # ══════════════════════════════════════════════════════════════════════════
    # MIGRI.FI — Finnish Immigration Service
    # ══════════════════════════════════════════════════════════════════════════

    # Overview
    "https://migri.fi/en/types-of-residence-permits",
    "https://migri.fi/en/continuous-permit",
    "https://migri.fi/en/temporary-permit",
    "https://migri.fi/en/d-permit",
    "https://migri.fi/en/residence-permit",
    "https://migri.fi/en/first-residence-permit",
    "https://migri.fi/en/i-want-to-apply",
    "https://migri.fi/en/i-want-a-residence-permit",
    "https://migri.fi/en/permits-and-citizenship",
    "https://migri.fi/en/after-applying",
    "https://migri.fi/en/faq-residence-permits",
    "https://migri.fi/en/faq",
    "https://migri.fi/en/glossary",

    # Work permits
    "https://migri.fi/en/coming-to-finland-for-work",
    "https://migri.fi/en/coming-to-finland-for-work/applications",
    "https://migri.fi/en/residence-permit-for-an-employed-person",
    "https://migri.fi/en/guide-for-employed-persons",
    "https://migri.fi/en/entrepreneur",
    "https://migri.fi/en/start-up-entrepreneur",
    "https://migri.fi/en/specialist",
    "https://migri.fi/en/eu-blue-card",
    "https://migri.fi/en/internship",
    "https://migri.fi/en/seasonal-work",
    "https://migri.fi/en/residence-permit-for-seasonal-work",
    "https://migri.fi/en/working-holiday/en",
    "https://migri.fi/en/internal-transfer-within-a-company",
    "https://migri.fi/en/au-pair/en",
    "https://migri.fi/en/volunteering",
    "https://migri.fi/en/work-in-finland",
    "https://migri.fi/en/for-employers",
    "https://migri.fi/en/income-requirement",
    "https://migri.fi/en/working-in-finland/income-requirement",
    "https://migri.fi/en/incomes-register",
    "https://migri.fi/en/right-to-work",

    # Fast track
    "https://migri.fi/en/fast-track",
    "https://migri.fi/en/i-want-to-fast-track-my-application",
    "https://migri.fi/en/fast-track-for-specialist",
    "https://migri.fi/en/fast-track-for-eu-blue-card",
    "https://migri.fi/en/fast-track-for-startup-entrepreneur",
    "https://migri.fi/en/fast-track-for-family-member",
    "https://migri.fi/en/fast-track-instructions-for-employers",

    # Study & Research
    "https://migri.fi/en/studying-in-finland",
    "https://migri.fi/en/residence-permit-application-for-studies",
    "https://migri.fi/en/guide-for-students",
    "https://migri.fi/en/income-requirement-for-students",
    "https://migri.fi/en/after-graduation",
    "https://migri.fi/en/moving-to-finland-as-a-researcher",
    "https://migri.fi/en/researcher",
    "https://migri.fi/en/instructions-for-scientific-researchers",
    "https://migri.fi/en/residence-permit-to-look-for-work",
    "https://migri.fi/en/degree-completed-in-finland",

    # Family reunification
    "https://migri.fi/en/moving-to-finland-to-be-with-a-family-member",
    "https://migri.fi/en/spouse-is-a-finnish-citizen",
    "https://migri.fi/en/spouse-in-finland-with-a-residence-permit",
    "https://migri.fi/en/cohabiting-partner-is-a-finnish-citizen",
    "https://migri.fi/en/my-child-is-a-finnish-citizen",
    "https://migri.fi/en/child-in-finland-with-a-residence-permit",
    "https://migri.fi/en/income-requirement-for-family-members-of-a-person-who-has-been-granted-a-residence-permit-in-finland",
    "https://migri.fi/en/dna-analysis-for-family-members",
    "https://migri.fi/en/amendments-to-family-reunification-provisions-2025",
    "https://migri.fi/en/family-member-of-a-foreign-national",
    "https://migri.fi/en/family-member-of-a-finnish-citizen",

    # Extending permit
    "https://migri.fi/en/extended-permit",
    "https://migri.fi/en/i-want-to-extend-my-residence-permit",
    "https://migri.fi/en/extended-permit-on-the-basis-of-work",
    "https://migri.fi/en/extended-permit-for-studies",
    "https://migri.fi/en/extended-permit-for-family-members",

    # Permanent residence
    "https://migri.fi/en/permanent-residence-permit",
    "https://migri.fi/en/language-skills-requirement",
    "https://migri.fi/en/period-of-residence-requirement",
    "https://migri.fi/en/work-history-requirement",
    "https://migri.fi/en/i-want-a-permanent-residence-permit",

    # EU citizens
    "https://migri.fi/en/eu-citizen",
    "https://migri.fi/en/i-am-an-eu-citizen",
    "https://migri.fi/en/i-am-a-family-member-of-an-eu-citizen",
    "https://migri.fi/en/i-am-an-eu-citizen-or-a-family-member",
    "https://migri.fi/en/registration-of-right-of-residence",
    "https://migri.fi/en/i-want-a-permanent-right-of-residence",
    "https://migri.fi/en/i-am-a-nordic-citizen",

    # Citizenship
    "https://migri.fi/en/finnish-citizenship",
    "https://migri.fi/en/i-want-to-become-a-finnish-citizen",
    "https://migri.fi/en/requirements-for-citizenship",
    "https://migri.fi/en/citizenship-declaration",
    "https://migri.fi/en/dual-citizenship",
    "https://migri.fi/en/citizenship-by-declaration",
    "https://migri.fi/en/losing-finnish-citizenship",

    # Asylum & Protection
    "https://migri.fi/en/asylum-in-finland",
    "https://migri.fi/en/asylum",
    "https://migri.fi/en/temporary-protection",
    "https://migri.fi/en/reception-of-asylum-seekers",

    # Processing, admin & decisions
    "https://migri.fi/en/processing-of-applications",
    "https://migri.fi/en/processing-times",
    "https://migri.fi/en/check-the-processing-time-of-your-application",
    "https://migri.fi/en/processing-fees",
    "https://migri.fi/en/appealing-a-decision",
    "https://migri.fi/en/informing-of-the-decision",
    "https://migri.fi/en/changes-and-supplementary-documents",
    "https://migri.fi/en/requests-and-certificates",
    "https://migri.fi/en/cancellation-of-a-permit",
    "https://migri.fi/en/withdrawal-of-applications-or-permits",
    "https://migri.fi/en/denial-of-admittance-or-stay-deportation-entry-ban",
    "https://migri.fi/en/procedural-provisions",
    "https://migri.fi/en/legislation",
    "https://migri.fi/en/travel-documents",
    "https://migri.fi/en/biometric-data",
    "https://migri.fi/en/documents-required",
    "https://migri.fi/en/identity-investigation",

    # ══════════════════════════════════════════════════════════════════════════
    # INFOFINLAND.FI — Government integration portal
    # ══════════════════════════════════════════════════════════════════════════

    "https://infofinland.fi/en/moving-to-finland",
    "https://infofinland.fi/en/moving-to-finland/moving-to-finland-checklist",
    "https://infofinland.fi/en/moving-to-finland/non-eu-citizens",
    "https://infofinland.fi/en/moving-to-finland/non-eu-citizens/permanent-residence-permit",
    "https://infofinland.fi/en/moving-to-finland/non-eu-citizens/asylum-in-finland",
    "https://infofinland.fi/en/moving-to-finland/non-eu-citizens/study-in-finland",
    "https://infofinland.fi/en/moving-to-finland/nordic-citizens",
    "https://infofinland.fi/en/moving-to-finland/eu-eea-citizens",
    "https://infofinland.fi/en/settling-in-finland",
    "https://infofinland.fi/en/settling-in-finland/finnish-social-security",
    "https://infofinland.fi/en/settling-in-finland/cost-of-living-in-finland",
    "https://infofinland.fi/en/settling-in-finland/moving-away-from-finland",
    "https://infofinland.fi/en/settling-in-finland/municipality-of-residence-in-finland",
    "https://infofinland.fi/en/settling-in-finland/taxation-in-finland",
    "https://infofinland.fi/en/settling-in-finland/banking-in-finland",
    "https://infofinland.fi/en/settling-in-finland/integration",
    "https://infofinland.fi/en/work-and-enterprise",
    "https://infofinland.fi/en/work-and-enterprise/during-employment/employment-contract-and-terms-of-employment",
    "https://infofinland.fi/en/work-and-enterprise/during-employment/wages-and-working-hours",
    "https://infofinland.fi/en/work-and-enterprise/looking-for-work",
    "https://infofinland.fi/en/work-and-enterprise/starting-a-business",
    "https://infofinland.fi/en/housing/housing-in-finland",
    "https://infofinland.fi/en/housing/housing-allowance",
    "https://infofinland.fi/en/health/health-services-in-finland",
    "https://infofinland.fi/en/health/using-health-services",
    "https://infofinland.fi/en/education/foreign-students-in-finland",
    "https://infofinland.fi/en/family/family-in-finland",
    "https://infofinland.fi/en/family/having-a-child-in-finland",

    # ══════════════════════════════════════════════════════════════════════════
    # KELA.FI — Social Insurance Institution
    # ══════════════════════════════════════════════════════════════════════════

    "https://www.kela.fi/coming-to-finland",
    "https://www.kela.fi/moving-to-finland",
    "https://www.kela.fi/when-you-move-to-finland",
    "https://www.kela.fi/can-you-get-benefits-when-you-move-to-finland",
    "https://www.kela.fi/benefits-available-from-kela",
    "https://www.kela.fi/kela-card",
    "https://www.kela.fi/unemployment",
    "https://www.kela.fi/unemployment-benefits",
    "https://www.kela.fi/basic-unemployment-allowance",
    "https://www.kela.fi/jobseekers-allowance",
    "https://www.kela.fi/housing-allowance",
    "https://www.kela.fi/general-housing-allowance",
    "https://www.kela.fi/social-assistance",
    "https://www.kela.fi/social-assistance-can-you-get-it",
    "https://www.kela.fi/social-assistance-foreign-residents",
    "https://www.kela.fi/child-benefit",
    "https://www.kela.fi/parental-benefit",
    "https://www.kela.fi/sickness-allowance",
    "https://www.kela.fi/national-pension",
    "https://www.kela.fi/financial-aid-for-students-eligibility",
    "https://www.kela.fi/web/en/international-situations-contact-information",
    "https://www.kela.fi/rehabilitation",
    "https://www.kela.fi/disability-benefits",
    "https://www.kela.fi/earnings-related-unemployment-insurance",

    # ══════════════════════════════════════════════════════════════════════════
    # DVV.FI — Digital and Population Data Services Agency
    # ══════════════════════════════════════════════════════════════════════════

    "https://dvv.fi/en/as-a-foreigner-in-finland",
    "https://dvv.fi/en/foreigner-registration",
    "https://dvv.fi/en/municipality-of-residence",
    "https://dvv.fi/en/personal-identity-code",
    "https://dvv.fi/en/notifications",
    "https://dvv.fi/en/changing-your-personal-identity-code",
    "https://dvv.fi/en/international-moving",
    "https://dvv.fi/en/guide-for-employed-persons",
    "https://dvv.fi/en/guide-for-students",
    "https://dvv.fi/en/fast-track-service-for-specialists-and-growth-entrepreneurs",
    "https://dvv.fi/en/registering-your-address",
    "https://dvv.fi/en/family-relationships",

    # ══════════════════════════════════════════════════════════════════════════
    # VERO.FI — Finnish Tax Administration
    # ══════════════════════════════════════════════════════════════════════════

    "https://www.vero.fi/en/individuals/tax-cards-and-tax-returns/arriving_in_finland/",
    "https://www.vero.fi/en/individuals/tax-cards-and-tax-returns/arriving_in_finland/moving-to-finland/",
    "https://www.vero.fi/en/individuals/tax-cards-and-tax-returns/arriving_in_finland/income-taxes-in-finland/",
    "https://www.vero.fi/en/individuals/tax-cards-and-tax-returns/arriving_in_finland/work_in_finland/",
    "https://www.vero.fi/en/individuals/tax-cards-and-tax-returns/arriving_in_finland/individuals-residency-and-nonresidency-in-finland/",
    "https://www.vero.fi/en/individuals/tax-cards-and-tax-returns/arriving_in_finland/work_in_finland/finnish-employer/",
    "https://www.vero.fi/en/individuals/tax-cards-and-tax-returns/arriving_in_finland/work_in_finland/foreign-employer/",
    "https://www.vero.fi/en/individuals/tax-cards-and-tax-returns/arriving_in_finland/work_in_finland/specific-instructions-for-different-occupations/working-in-finland-as-a-self-employed-person/",
    "https://www.vero.fi/en/individuals/tax-cards-and-tax-returns/arriving_in_finland/work_in_finland/finnish-personal-identity-codes-for-workers-arriving-in-finland/",
    "https://www.vero.fi/en/individuals/tax-cards-and-tax-returns/arriving_in_finland/work_in_finland/specific-instructions-for-different-occupations/key_employees_from_other_countrie/",
    "https://www.vero.fi/en/individuals/tax-cards-and-tax-returns/tax-card/",

    # ══════════════════════════════════════════════════════════════════════════
    # SUOMI.FI — Finnish Government Services Portal
    # The /en/life-situations/* structure no longer exists; portal is now
    # primarily a Finnish-language e-services hub.
    # ══════════════════════════════════════════════════════════════════════════

    "https://www.suomi.fi/frontpage",

    # ══════════════════════════════════════════════════════════════════════════
    # ENTERFINLAND.FI — Online Application Portal (NEW)
    # ══════════════════════════════════════════════════════════════════════════

    "https://enterfinland.fi/eServices",

    # ══════════════════════════════════════════════════════════════════════════
    # TE-PALVELUT.FI — Employment Services
    # ══════════════════════════════════════════════════════════════════════════

    "https://www.te-palvelut.fi/en/jobseekers/support-finding-job/integration-services-for-immigrants",
    "https://toimistot.te-palvelut.fi/en/information-for-new-immigrants",

    # ══════════════════════════════════════════════════════════════════════════
    # WORKINFINLAND.EU — Official Talent Boost portal
    # ══════════════════════════════════════════════════════════════════════════

    "https://www.workinfinland.eu/en/coming-to-finland/",
    "https://www.workinfinland.eu/en/coming-to-finland/residence-permit/",
    "https://www.workinfinland.eu/en/coming-to-finland/after-arrival/",
    "https://www.workinfinland.eu/en/living-in-finland/",
    "https://www.workinfinland.eu/en/living-in-finland/social-security-and-healthcare/",
    "https://www.workinfinland.eu/en/living-in-finland/taxation/",
    "https://www.workinfinland.eu/en/living-in-finland/housing/",
    "https://www.workinfinland.eu/en/living-in-finland/banking/",

    # ══════════════════════════════════════════════════════════════════════════
    # IHHELSINKI.FI — International House Helsinki
    # ══════════════════════════════════════════════════════════════════════════

    "https://ihhelsinki.fi/services/",
    "https://ihhelsinki.fi/services/social-security-benefits/",
    "https://ihhelsinki.fi/services/residence-permits/",
    "https://ihhelsinki.fi/services/tax-administration/",
    "https://ihhelsinki.fi/services/employment-and-enterprise/",

    # ══════════════════════════════════════════════════════════════════════════
    # POLIISI.FI — Finnish Police (passports, IDs, driving licences)
    # ══════════════════════════════════════════════════════════════════════════

    "https://poliisi.fi/en/passports-identity-cards-and-permits",
    "https://poliisi.fi/en/passport",
    "https://poliisi.fi/en/identity-card",
    "https://poliisi.fi/en/how-to-apply-for-an-identity-card",
    "https://poliisi.fi/en/using-your-passport",

    # ══════════════════════════════════════════════════════════════════════════
    # TULLI.FI — Finnish Customs
    # ══════════════════════════════════════════════════════════════════════════

    "https://tulli.fi/en/individuals/moving",
    "https://tulli.fi/en/individuals/moving/to-finland",
    "https://tulli.fi/en/individuals/moving/how-to-declare-removal-goods",
    "https://tulli.fi/en/individuals/moving/goods-imported-by-a-student-arriving-in-finland",
    "https://tulli.fi/en/restrictions/pets",
    "https://tulli.fi/en/restrictions/pets/moving",
    "https://tulli.fi/en/restrictions/pets/travelling",
    "https://tulli.fi/en/restrictions/cars/moving",
    "https://tulli.fi/en/individuals/going-to-order-goods-from-abroad",

    # ══════════════════════════════════════════════════════════════════════════
    # TYOSUOJELU.FI — Occupational Safety & Worker Rights
    # ══════════════════════════════════════════════════════════════════════════

    "https://www.tyosuojelu.fi/en/employment-relationship",
    "https://www.tyosuojelu.fi/en/employment-relationship/working-hours",
    "https://www.tyosuojelu.fi/en/employment-relationship/employment-contract",
    "https://www.tyosuojelu.fi/en/employment-relationship/pay",
    "https://www.tyosuojelu.fi/en/employment-relationship/termination",
    "https://www.tyosuojelu.fi/en/working-conditions",
    "https://www.tyosuojelu.fi/en/occupational-health",

    # ══════════════════════════════════════════════════════════════════════════
    # TYOMARKKINATORI.FI — Employment Services (replaced te-palvelut.fi)
    # ══════════════════════════════════════════════════════════════════════════

    "https://tyomarkkinatori.fi/en/personal-customers",
    "https://tyomarkkinatori.fi/en/personal-customers/work-life-information",
    "https://tyomarkkinatori.fi/en/personal-customers/looking-for-work",
    "https://tyomarkkinatori.fi/en/personal-customers/integration-services",
]


# ── Domain helpers ─────────────────────────────────────────────────────────────

def _get_domain_key(url: str) -> str | None:
    """Return the DOMAIN_CONFIGS key for a URL, or None if unknown."""
    netloc = urlparse(url).netloc.lower()
    # Match longest key first (subdomain before parent domain)
    for domain_key in DOMAIN_CONFIGS:
        if domain_key in netloc:
            return domain_key
    return None


def _get_config(url: str) -> dict | None:
    key = _get_domain_key(url)
    return DOMAIN_CONFIGS.get(key) if key else None


def is_crawlable(url: str) -> bool:
    """Return True if this URL is valid for crawling."""
    url_lower = url.lower()

    # Global skip patterns
    for skip in GLOBAL_SKIP:
        if skip in url_lower:
            return False

    config = _get_config(url)
    if not config:
        return False

    # Domain-specific skip patterns
    for skip in config.get("skip", []):
        if skip in url_lower:
            return False

    # Language prefix requirement
    lang_prefix = config.get("lang_prefix")
    if lang_prefix:
        path = urlparse(url).path
        if not path.startswith(lang_prefix):
            return False

    # Reject trivially short paths (just the domain root)
    path = urlparse(url).path
    if len(path.rstrip("/")) < 3:
        return False

    return True


# ── Table → readable text ──────────────────────────────────────────────────────

def convert_tables_to_text(soup: BeautifulSoup) -> None:
    """
    Replace HTML tables with pipe-formatted plain text in-place.

    This preserves income thresholds, fee schedules, and requirement tables
    that are otherwise destroyed by plain get_text() extraction.

    Example output:
      Family size | Helsinki region | Rest of Finland
      Sponsor only | €1,210 | €900
      Sponsor + spouse | €1,820 | €1,400
    """
    for table in soup.find_all("table"):
        rows = []
        header_written = False
        for tr in table.find_all("tr"):
            ths = tr.find_all("th")
            tds = tr.find_all("td")
            cells = ths if ths else tds
            if not cells:
                continue
            cell_texts = [
                " ".join(c.get_text(separator=" ", strip=True).split()) or "–"
                for c in cells
            ]
            # Skip rows that are entirely empty or just dashes
            if all(t in ("–", "", "-") for t in cell_texts):
                continue
            rows.append(" | ".join(cell_texts))
            # Add a separator line after the header row
            if ths and not header_written:
                rows.append("-" * min(60, sum(len(t) + 3 for t in cell_texts)))
                header_written = True

        if rows:
            tag = soup.new_tag("p")
            tag.string = "\n".join(rows)
            table.replace_with(tag)
        else:
            table.decompose()


# ── Link extraction ────────────────────────────────────────────────────────────

def extract_links(soup: BeautifulSoup, base_url: str) -> list[str]:
    """Return crawlable sublinks found on this page, within the same domain."""
    base_domain_key = _get_domain_key(base_url)
    if not base_domain_key:
        return []

    found = set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href:
            continue

        # Skip fragment-only and obvious non-links
        if href.startswith(("#", "mailto:", "tel:", "javascript:", "data:")):
            continue

        # Resolve relative URLs and strip fragment
        full_url = urljoin(base_url, href).split("#")[0].rstrip("/")
        if not full_url:
            continue

        # Must belong to same domain
        if _get_domain_key(full_url) != base_domain_key:
            continue

        if is_crawlable(full_url):
            found.add(full_url)

    return list(found)


# ── Text extraction ────────────────────────────────────────────────────────────

def clean_text(text: str) -> str:
    """Collapse excess whitespace while preserving paragraph structure."""
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    lines = [line.rstrip() for line in text.splitlines()]
    cleaned, prev_blank = [], False
    for line in lines:
        if not line:
            if not prev_blank:
                cleaned.append("")
            prev_blank = True
        else:
            cleaned.append(line)
            prev_blank = False
    return "\n".join(cleaned).strip()


def extract_content(resp_text: str, url: str) -> tuple[str, str, BeautifulSoup | None]:
    """
    Parse HTML and return (title, content, soup).
    soup is returned so the caller can extract links.
    Returns ('', '', None) if extraction fails or content is too short.
    """
    soup = BeautifulSoup(resp_text, "html.parser")

    # Convert tables to readable text BEFORE removing noise tags
    convert_tables_to_text(soup)

    for tag in soup(NOISE_TAGS):
        tag.decompose()

    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else url

    main = (
        soup.find("main")
        or soup.find("article")
        or soup.find(id="content")
        or soup.find(class_="content")
        or soup.find(class_="main-content")
        or soup.find("body")
    )
    raw_text = main.get_text(separator="\n") if main else soup.get_text(separator="\n")
    content  = clean_text(raw_text)

    if not content or len(content) < 120:
        return "", "", None

    return title, content, soup


# ── Page fetcher ───────────────────────────────────────────────────────────────

def fetch_page(url: str) -> tuple[dict | None, BeautifulSoup | None]:
    """
    Fetch a URL and return ({url, title, content}, soup) or (None, None) on failure.
    soup is used by the caller for link discovery.
    """
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    except requests.RequestException as exc:
        log.warning("Request failed — %s | %s", url, exc)
        return None, None

    if resp.status_code == 429:
        log.warning("Rate limited (429) — %s — pausing 10s", url)
        time.sleep(10)
        return None, None

    if resp.status_code != 200:
        log.warning("HTTP %d — skipping %s", resp.status_code, url)
        return None, None

    title, content, soup = extract_content(resp.text, url)
    if not content:
        log.warning("No content extracted from %s — skipping", url)
        return None, None

    log.info("✓  %-70s  (%d chars)", url[-70:], len(content))
    return {"url": url, "title": title, "content": content}, soup


# ── Main crawler ───────────────────────────────────────────────────────────────

def crawl_all() -> list[dict]:
    """
    BFS crawl across all configured domains.

    Process:
      1. Seed URLs are added to per-domain queues (seeds processed first).
      2. After each page is scraped, discovered sublinks are added to the queue.
      3. Each domain stops when its page cap is reached.
    """
    visited: set[str]              = set()
    queues:  dict[str, deque]      = {}
    counts:  dict[str, int]        = {}
    pages:   list[dict]            = []

    # Initialise queues with seed URLs
    for raw_url in SEED_URLS:
        url = raw_url.rstrip("/")
        if url in visited:
            continue
        if not is_crawlable(url):
            log.debug("Seed URL not crawlable — skipping: %s", url)
            continue
        domain = _get_domain_key(url)
        if not domain:
            continue
        if domain not in queues:
            queues[domain] = deque()
            counts[domain] = 0
        visited.add(url)
        queues[domain].appendleft(url)  # seeds at front

    total_domains = len(queues)
    log.info("Starting crawl across %d domains, %d seed URLs", total_domains, len(visited))

    # Round-robin BFS across domains so no single domain blocks others
    while any(q for q in queues.values()):
        for domain in list(queues.keys()):
            q = queues.get(domain)
            if not q:
                continue

            max_p = DOMAIN_CONFIGS.get(domain, {}).get("max_pages", 30)
            if counts.get(domain, 0) >= max_p:
                q.clear()
                continue

            url = q.popleft()

            page, soup = fetch_page(url)
            if page:
                pages.append(page)
                counts[domain] = counts.get(domain, 0) + 1

                # Discover and queue sublinks
                if soup:
                    new_links = extract_links(soup, url)
                    added = 0
                    for link in new_links:
                        link_clean = link.rstrip("/")
                        if link_clean not in visited:
                            link_domain = _get_domain_key(link_clean)
                            if link_domain == domain:  # same domain only
                                lim = DOMAIN_CONFIGS.get(domain, {}).get("max_pages", 30)
                                if counts.get(domain, 0) + len(q) < lim:
                                    visited.add(link_clean)
                                    q.append(link_clean)
                                    added += 1
                    if added:
                        log.debug("  → queued %d new links from %s", added, url[-60:])

            time.sleep(REQUEST_DELAY)

    # Summary
    log.info("── Crawl summary ──────────────────────────────────────")
    for domain, count in sorted(counts.items(), key=lambda x: -x[1]):
        log.info("  %-35s %d pages", domain, count)
    log.info("  Total pages scraped: %d", len(pages))

    return pages


# ── PDF extraction ─────────────────────────────────────────────────────────────

def extract_pdf(pdf_path: Path) -> dict | None:
    """Extract full text from a PDF file using PyMuPDF."""
    try:
        doc = fitz.open(str(pdf_path))
    except Exception as exc:
        log.warning("Could not open %s — %s", pdf_path.name, exc)
        return None

    pages_text = [doc.load_page(i).get_text("text") for i in range(len(doc))]
    doc.close()

    full_text = clean_text("\n".join(pages_text))
    if not full_text:
        log.warning("No text extracted from %s — skipping", pdf_path.name)
        return None

    log.info("✓  PDF: %-60s  (%d chars)", pdf_path.name, len(full_text))
    return {"source": pdf_path.name, "content": full_text}


def extract_pdfs() -> list[dict]:
    pdf_files = sorted(PDF_DIR.glob("*.pdf"))
    if not pdf_files:
        log.info("No PDFs found in %s — skipping PDF extraction", PDF_DIR)
        return []
    return [r for p in pdf_files if (r := extract_pdf(p)) is not None]


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    log.info("=== FinnPermit Guide — Stage 1: Data Collection v2 ===")

    pages = crawl_all()
    with open(PAGES_OUT, "w", encoding="utf-8") as f:
        json.dump(pages, f, ensure_ascii=False, indent=2)
    log.info("Web pages saved : %d  →  %s", len(pages), PAGES_OUT)

    log.info("Extracting PDFs …")
    pdf_data = extract_pdfs()
    with open(PDF_OUT, "w", encoding="utf-8") as f:
        json.dump(pdf_data, f, ensure_ascii=False, indent=2)
    log.info("PDFs saved      : %d  →  %s", len(pdf_data), PDF_OUT)

    log.info("=== Stage 1 complete ===")


if __name__ == "__main__":
    main()
