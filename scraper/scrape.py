"""
MigriGuide - Stage 1: Data Collection
Scrapes official Finnish immigration sources and extracts PDF text.

Sources covered:
  - Migri.fi        (Finnish Immigration Service — primary authority)
  - InfoFinland.fi  (Government integration portal)
  - EnterFinland.fi (Official application portal)
  - Kela.fi         (Social insurance — benefits for immigrants)
  - DVV.fi          (Population register — mandatory post-permit step)
  - TE-palvelut.fi  (Employment services)
  - Vero.fi         (Tax administration)
  - Suomi.fi        (Government service directory)

Outputs:
  data/raw/migri_pages.json   ← all scraped web pages
  data/raw/pdf_content.json   ← text extracted from PDFs in data/raw/pdfs/
"""

import json
import logging
import time
from pathlib import Path

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
REQUEST_DELAY = 1  # seconds between requests — be polite to servers
TIMEOUT       = 25

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; MigriGuide-Bot/1.0; "
        "educational/non-commercial; +https://github.com/Rohitn96/migri-guide)"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

# ── Tags to strip before text extraction ──────────────────────────────────────
NOISE_TAGS = [
    "nav", "footer", "header", "script", "style", "noscript",
    "aside", "form", "button", "iframe", "svg", "figure",
    "cookie-consent", "breadcrumb",
]

# ── URLs ───────────────────────────────────────────────────────────────────────
# Grouped by source for readability. All are English-language official pages.

URLS = [

    # ══════════════════════════════════════════════════════════════════════════
    # MIGRI.FI — Finnish Immigration Service (primary authority)
    # All URLs verified from migri.fi/en/sitemap (live May 2026)
    # ══════════════════════════════════════════════════════════════════════════

    # Navigation / overview pages — good entry points with links to sub-pages
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

    # Extending permit
    "https://migri.fi/en/extended-permit",
    "https://migri.fi/en/i-want-to-extend-my-residence-permit",
    "https://migri.fi/en/extended-permit-on-the-basis-of-work",
    "https://migri.fi/en/extended-permit-for-studies",

    # Permanent residence — main page + all integration requirement sub-pages
    "https://migri.fi/en/permanent-residence-permit",
    "https://migri.fi/en/language-skills-requirement",
    "https://migri.fi/en/period-of-residence-requirement",
    "https://migri.fi/en/work-history-requirement",

    # EU citizens
    "https://migri.fi/en/eu-citizen",
    "https://migri.fi/en/i-am-an-eu-citizen",
    "https://migri.fi/en/i-am-a-family-member-of-an-eu-citizen",
    "https://migri.fi/en/i-am-an-eu-citizen-or-a-family-member",
    "https://migri.fi/en/registration-of-right-of-residence",
    "https://migri.fi/en/i-want-a-permanent-right-of-residence",
    "https://migri.fi/en/i-am-a-nordic-citizen",

    # Citizenship — main page + requirements sub-pages
    "https://migri.fi/en/finnish-citizenship",
    "https://migri.fi/en/i-want-to-become-a-finnish-citizen",
    "https://migri.fi/en/requirements-for-citizenship",
    "https://migri.fi/en/citizenship-declaration",
    "https://migri.fi/en/dual-citizenship",

    # Asylum & Protection
    "https://migri.fi/en/asylum-in-finland",
    "https://migri.fi/en/asylum",
    "https://migri.fi/en/temporary-protection",

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
    "https://migri.fi/en/processing-fees",

    # ══════════════════════════════════════════════════════════════════════════
    # INFOFINLAND.FI — Government integration portal
    # All URLs verified from search results (live May 2026)
    # ══════════════════════════════════════════════════════════════════════════

    # Moving to Finland section
    "https://infofinland.fi/en/moving-to-finland",
    "https://infofinland.fi/en/moving-to-finland/moving-to-finland-checklist",
    "https://infofinland.fi/en/moving-to-finland/non-eu-citizens",
    "https://infofinland.fi/en/moving-to-finland/non-eu-citizens/permanent-residence-permit",
    "https://infofinland.fi/en/moving-to-finland/non-eu-citizens/asylum-in-finland",
    "https://infofinland.fi/en/moving-to-finland/non-eu-citizens/study-in-finland",
    "https://infofinland.fi/en/moving-to-finland/nordic-citizens",

    # Settling in Finland section
    "https://infofinland.fi/en/settling-in-finland/finnish-social-security",
    "https://infofinland.fi/en/settling-in-finland/cost-of-living-in-finland",
    "https://infofinland.fi/en/settling-in-finland/moving-away-from-finland",

    # Work section
    "https://infofinland.fi/en/work-and-enterprise/during-employment/employment-contract-and-terms-of-employment",
    "https://infofinland.fi/en/work-and-enterprise/during-employment/wages-and-working-hours",

    # Housing section
    "https://infofinland.fi/en/housing/housing-in-finland",
    "https://infofinland.fi/en/housing/housing-allowance",

    # Health section
    "https://infofinland.fi/en/health/health-services-in-finland",

    # Education section
    "https://infofinland.fi/en/education/foreign-students-in-finland",

    # Family section
    "https://infofinland.fi/en/family/family-in-finland",

    # Additional settling pages
    "https://infofinland.fi/en/settling-in-finland/municipality-of-residence-in-finland",
    "https://infofinland.fi/en/settling-in-finland/taxation-in-finland",
    "https://infofinland.fi/en/settling-in-finland/banking-in-finland",
    "https://infofinland.fi/en/settling-in-finland/integration",
    "https://infofinland.fi/en/work-and-enterprise/looking-for-work",
    "https://infofinland.fi/en/work-and-enterprise/starting-a-business",
    "https://infofinland.fi/en/health/using-health-services",

    # ══════════════════════════════════════════════════════════════════════════
    # KELA.FI — Social Insurance Institution
    # All URLs verified from search results (live May 2026)
    # Note: Kela simplified their URL structure — old /web/en/ prefix removed
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

    # ══════════════════════════════════════════════════════════════════════════
    # DVV.FI — Digital and Population Data Services Agency
    # All URLs verified from search results (live May 2026)
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

    # ══════════════════════════════════════════════════════════════════════════
    # VERO.FI — Finnish Tax Administration
    # All URLs verified from search results (live May 2026)
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

    # ══════════════════════════════════════════════════════════════════════════
    # TE-PALVELUT.FI — Employment and Economic Development Services
    # All URLs verified from search results (live May 2026)
    # ══════════════════════════════════════════════════════════════════════════

    "https://www.te-palvelut.fi/en/jobseekers/support-finding-job/integration-services-for-immigrants",
    "https://toimistot.te-palvelut.fi/en/information-for-new-immigrants",

    # ══════════════════════════════════════════════════════════════════════════
    # WORKINFINLAND.EU — Official Talent Boost portal
    # Finnish government portal specifically for international specialists
    # ══════════════════════════════════════════════════════════════════════════

    "https://www.workinfinland.eu/en/coming-to-finland/",
    "https://www.workinfinland.eu/en/coming-to-finland/residence-permit/",
    "https://www.workinfinland.eu/en/coming-to-finland/after-arrival/",
    "https://www.workinfinland.eu/en/living-in-finland/",
    "https://www.workinfinland.eu/en/living-in-finland/social-security-and-healthcare/",
    "https://www.workinfinland.eu/en/living-in-finland/taxation/",

    # ══════════════════════════════════════════════════════════════════════════
    # IHHELSINKI.FI — International House Helsinki
    # One-stop service point for immigrants in Helsinki, run by City of Helsinki
    # ══════════════════════════════════════════════════════════════════════════

    "https://ihhelsinki.fi/services/",
    "https://ihhelsinki.fi/services/social-security-benefits/",
    "https://ihhelsinki.fi/services/residence-permits/",

    # ══════════════════════════════════════════════════════════════════════════
    # POLIISI.FI — Finnish Police
    # Passports, ID cards, alien's passport, refugee travel document,
    # and foreign driving licence exchange — all handled by police, not Migri
    # ══════════════════════════════════════════════════════════════════════════

    "https://poliisi.fi/en/passport",
    "https://poliisi.fi/en/identity-card",
    "https://poliisi.fi/en/alien-s-passport",
    "https://poliisi.fi/en/refugee-travel-document",
    "https://poliisi.fi/en/driving-licence",
    "https://poliisi.fi/en/foreign-driving-licences",
    "https://poliisi.fi/en/passport-and-identity-card-for-a-minor",

    # ══════════════════════════════════════════════════════════════════════════
    # TULLI.FI — Finnish Customs
    # Moving household goods, importing vehicles/pets — asked by new residents
    # ══════════════════════════════════════════════════════════════════════════

    "https://tulli.fi/en/private-persons/moving-to-finland",
    "https://tulli.fi/en/private-persons/vehicles",
    "https://tulli.fi/en/private-persons/pets",
    "https://tulli.fi/en/private-persons/goods-for-private-use",

    # ══════════════════════════════════════════════════════════════════════════
    # TYOSUOJELU.FI — Occupational Safety & Worker Rights
    # Foreign employee rights, employment contracts, minimum wage, working hours
    # ══════════════════════════════════════════════════════════════════════════

    "https://www.tyosuojelu.fi/en/work-relationship",
    "https://www.tyosuojelu.fi/en/work-relationship/foreign-employee",
    "https://www.tyosuojelu.fi/en/work-relationship/sent-worker",
    "https://www.tyosuojelu.fi/en/working-conditions",
    "https://www.tyosuojelu.fi/en/worker-protection",

    # ══════════════════════════════════════════════════════════════════════════
    # TYOMARKKINATORI.FI — Employment Services (replaced te-palvelut.fi)
    # Job seeker services, integration training, TE-office support
    # ══════════════════════════════════════════════════════════════════════════

    "https://tyomarkkinatori.fi/en/personal-customers",
    "https://tyomarkkinatori.fi/en/personal-customers/work-life-information",
    "https://tyomarkkinatori.fi/en/personal-customers/looking-for-work",

]


# ── Scraping logic ─────────────────────────────────────────────────────────────

def clean_text(text: str) -> str:
    """Collapse whitespace while preserving paragraph structure."""
    import re
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


def extract_page(url: str) -> dict | None:
    """Fetch URL and return {url, title, content} or None on failure."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    except requests.RequestException as exc:
        log.warning("Request failed — %s | %s", url, exc)
        return None

    if resp.status_code != 200:
        log.warning("Non-200 (%d) — skipping %s", resp.status_code, url)
        return None

    soup = BeautifulSoup(resp.text, "html.parser")

    for tag in soup(NOISE_TAGS):
        tag.decompose()

    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else url

    # Prefer semantic content containers, fall back to body
    main = (
        soup.find("main")
        or soup.find("article")
        or soup.find(id="content")
        or soup.find(class_="content")
        or soup.find("body")
    )
    raw_text = main.get_text(separator="\n") if main else soup.get_text(separator="\n")
    content = clean_text(raw_text)

    if not content or len(content) < 100:
        log.warning("Too little content extracted from %s — skipping", url)
        return None

    log.info("✓  %-70s  (%d chars)", url, len(content))
    return {"url": url, "title": title, "content": content}


def scrape_pages() -> list[dict]:
    pages = []
    total = len(URLS)
    for i, url in enumerate(URLS):
        log.info("[%d/%d] %s", i + 1, total, url)
        result = extract_page(url)
        if result:
            pages.append(result)
        if i < total - 1:
            time.sleep(REQUEST_DELAY)
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
    log.info("=== MigriGuide Stage 1: Data Collection ===")
    log.info("Scraping %d URLs …", len(URLS))

    pages = scrape_pages()
    with open(PAGES_OUT, "w", encoding="utf-8") as f:
        json.dump(pages, f, ensure_ascii=False, indent=2)
    log.info("Web pages saved  : %d / %d  →  %s", len(pages), len(URLS), PAGES_OUT)

    log.info("Extracting PDFs …")
    pdf_data = extract_pdfs()
    with open(PDF_OUT, "w", encoding="utf-8") as f:
        json.dump(pdf_data, f, ensure_ascii=False, indent=2)
    log.info("PDFs saved       : %d  →  %s", len(pdf_data), PDF_OUT)

    log.info("=== Stage 1 complete ===")


if __name__ == "__main__":
    main()