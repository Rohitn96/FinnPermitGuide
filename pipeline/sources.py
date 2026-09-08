"""
Source catalogue — the single place that says what the knowledge base is made of.

Everything here is data, not logic. Adding a source means adding a DOMAIN entry
and some seed URLs; nothing else in the pipeline needs to change.

Page caps exist to bound crawl time, not to curate. When a domain sits exactly at
its cap the corpus becomes a lottery decided by link-discovery order, and rebuilds
silently swap pages in and out. Caps here are set comfortably above each domain's
observed English page count so they stay slack.
"""

# ── Crawl budget per domain ───────────────────────────────────────────────────
# lang_prefix : required URL path prefix for English pages (None = no restriction)
# max_pages   : ceiling on pages fetched from this domain
# skip        : reject any URL containing one of these substrings
#
# Longest key wins, so subdomains must be listed before their parent domain.
DOMAINS: dict[str, dict] = {
    "migri.fi": {
        "lang_prefix": "/en/",
        "max_pages": 500,
        "skip": ["/fi/", "/sv/", "/ar/", "/so/", "/ru/", "/sitemap", "?lang=", "/search"],
    },
    "infofinland.fi": {
        "lang_prefix": "/en/",
        "max_pages": 220,
        "skip": ["/fi/", "/sv/", "/ar/", "/so/", "/ru/", "/search", "?lang="],
    },
    "kela.fi": {
        "lang_prefix": None,
        "max_pages": 200,
        "skip": ["/fi/", "/sv/", "/ar/", "/ru/", "/web/fi", "/web/sv",
                 "/web/ar", "?lang=fi", "?lang=sv"],
    },
    "dvv.fi": {
        "lang_prefix": "/en/",
        "max_pages": 100,
        "skip": ["/fi/", "/sv/", "/ar/"],
    },
    "vero.fi": {
        "lang_prefix": "/en/",
        "max_pages": 120,
        "skip": ["/fi/", "/sv/", "/ar/", "?lang=", "/search"],
    },
    "suomi.fi": {
        "lang_prefix": None,
        "max_pages": 25,
        "skip": ["/fi/", "/sv/", "/ar/", "/ru/", "/so/", "/search", "?lang=",
                 "/palvelut/", "/lomakkeet/"],
    },
    "enterfinland.fi": {
        "lang_prefix": None,
        "max_pages": 25,
        "skip": ["/fi/", "/sv/", "login", "logout", "register",
                 "dashboard", "my-applications", "status", "pay"],
    },
    "ihhelsinki.fi": {
        "lang_prefix": None,
        "max_pages": 40,
        "skip": ["/fi/", "/sv/", "appointment", "booking", "varaa"],
    },
    "poliisi.fi": {
        "lang_prefix": "/en/",
        "max_pages": 80,
        # Only the documents side of the police is relevant here. /search and ?q=
        # are site-search result pages; the rest is licensing for guns, gambling
        # and private security, which no immigration question touches.
        "skip": ["/fi/", "/sv/", "/ru/", "/ar/", "/so/", "/search", "?q=",
                 "gambling", "firearm", "weapon", "hunting", "explosive",
                 "private-security", "lottery", "raffle"],
    },
    "traficom.fi": {
        "lang_prefix": "/en/",
        "max_pages": 50,
        # Traficom regulates transport broadly; only the driving-licence and
        # vehicle-registration side is relevant to someone moving to Finland.
        "skip": ["/fi/", "/sv/", "/aviation", "/maritime", "/rail", "/spectrum",
                 "/statistics", "/news", "/boating", "/merchant-shipping",
                 "/communications-networks", "/postal-services", "/fi-domains",
                 "/cyber-security", "/ai-regulation", "/hydrography", "/fairways"],
    },
    "tulli.fi": {
        "lang_prefix": "/en/",
        "max_pages": 70,
        # /businesses/ is commercial import-export procedure — a different
        # audience entirely from someone moving their belongings to Finland.
        "skip": ["/fi/", "/sv/", "/businesses/", "/en/businesses"],
    },
    "tyosuojelu.fi": {
        "lang_prefix": "/en/",
        "max_pages": 110,
        "skip": ["/fi/", "/sv/"],
    },
    "tyomarkkinatori.fi": {
        "lang_prefix": "/en/",
        "max_pages": 60,
        # /news/ and /careerstories/ publish Finnish-language articles under
        # an /en/ path, so lang_prefix does not catch them and they crowd out
        # the English jobseeker guidance that benefits answers depend on.
        "skip": ["/fi/", "/sv/", "/news/", "/careerstories/", "/tarinat/"],
    },
}

# Rejected on every domain.
GLOBAL_SKIP = [
    "#", "mailto:", "tel:", "javascript:", "data:",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".zip",
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".css", ".js", ".xml",
    # Trailing slashes matter: a bare "/register" also rejects legitimate
    # content paths such as dvv.fi/en/registering-your-address.
    "/logout/", "/login/", "/register/", "/admin/", "/404", "/403",
    "/logout?", "/login?", "/register?",
    "?print=", "?format=pdf", "?download=", "?share=",
    "/feed/", "/rss/", "/atom/",
]

# Domains deliberately not crawled, with the reason, so nobody re-adds them
# without solving the underlying problem.
EXCLUDED = {
    "workinfinland.eu":
        "Client-side rendered app shell. Every page returns an identical ~279 "
        "character HTML stub, so a static fetcher extracts nothing. Would need "
        "a headless browser to crawl.",
    "te-palvelut.fi":
        "Decommissioned. toimistot.te-palvelut.fi no longer resolves in DNS and "
        "the parent domain serves one page with no navigable links. Finland's "
        "employment services moved to tyomarkkinatori.fi, which is crawled.",
}

# ── Seed URLs ─────────────────────────────────────────────────────────────────
# Entry points. The crawler discovers the rest by following same-domain links.
# Anything a specific answer depends on belongs here rather than being left to
# discovery, because discovery order is not stable between runs.
SEEDS = [

    # ── migri.fi — Finnish Immigration Service ────────────────────────────────
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

    # Work
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
    "https://migri.fi/en/filling-in-the-terms-of-employment",

    # Fast track
    "https://migri.fi/en/fast-track",
    "https://migri.fi/en/i-want-to-fast-track-my-application",
    "https://migri.fi/en/fast-track-for-specialist",
    "https://migri.fi/en/fast-track-for-eu-blue-card",
    "https://migri.fi/en/fast-track-for-startup-entrepreneur",
    "https://migri.fi/en/fast-track-for-family-member",
    "https://migri.fi/en/fast-track-instructions-for-employers",

    # Study & research
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

    # Family
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

    # Extending
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
    # NB: /dual-citizenship, /citizenship-by-declaration and
    # /losing-finnish-citizenship all 404 at origin as of 2026-09-08.
    # /citizenship-application and /finnish-citizenship carry that content now.
    "https://migri.fi/en/finnish-citizenship",
    "https://migri.fi/en/citizenship-application",
    "https://migri.fi/en/i-want-to-become-a-finnish-citizen",
    "https://migri.fi/en/requirements-for-citizenship",
    "https://migri.fi/en/citizenship-declaration",

    # Asylum & protection
    "https://migri.fi/en/asylum-in-finland",
    "https://migri.fi/en/asylum",
    "https://migri.fi/en/temporary-protection",
    "https://migri.fi/en/reception-of-asylum-seekers",

    # Processing, admin, decisions
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

    # ── infofinland.fi — government integration portal ────────────────────────
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

    # ── kela.fi — Social Insurance Institution ────────────────────────────────
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
    "https://www.kela.fi/social-assistance-how-to-apply",
    "https://www.kela.fi/child-benefit",
    "https://www.kela.fi/parental-benefit",
    "https://www.kela.fi/sickness-allowance",
    "https://www.kela.fi/national-pension",
    "https://www.kela.fi/financial-aid-for-students-eligibility",
    "https://www.kela.fi/web/en/international-situations-contact-information",
    "https://www.kela.fi/rehabilitation",
    "https://www.kela.fi/disability-benefits",
    "https://www.kela.fi/earnings-related-unemployment-insurance",
    "https://www.kela.fi/medical-care-entitlement-finland",

    # ── dvv.fi — Digital and Population Data Services Agency ──────────────────
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

    # ── vero.fi — Finnish Tax Administration ──────────────────────────────────
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

    # ── suomi.fi / enterfinland.fi ────────────────────────────────────────────
    "https://www.suomi.fi/frontpage",
    "https://enterfinland.fi/eServices",

    # ── Employment services ───────────────────────────────────────────────────
    # tyomarkkinatori's landing page renders its nav client-side, so deep pages
    # are unreachable by link discovery and have to be seeded directly.
    "https://tyomarkkinatori.fi/en/personal-customers",
    "https://tyomarkkinatori.fi/en/personal-customers/information-about-working-life/search-for-work/services-to-support-job-seeking",
    "https://tyomarkkinatori.fi/en/personal-customers/information-about-working-life/search-for-work/tips-for-finding-a-job",
    "https://tyomarkkinatori.fi/en/personal-customers/information-about-working-life/search-for-work/registration-as-a-job-seeker",
    "https://tyomarkkinatori.fi/en/personal-customers/unemployment/the-rights-and-responsibilities-of-unemployed-job-seekers",

    # ── ihhelsinki.fi — International House Helsinki ──────────────────────────
    "https://ihhelsinki.fi/services/",
    "https://ihhelsinki.fi/services/social-security-benefits/",
    "https://ihhelsinki.fi/services/residence-permits/",
    "https://ihhelsinki.fi/services/tax-administration/",
    "https://ihhelsinki.fi/services/employment-and-enterprise/",

    # ── poliisi.fi — passports, ID cards, driving licences ────────────────────
    "https://poliisi.fi/en/passports-identity-cards-and-permits",
    "https://poliisi.fi/en/passport",
    "https://poliisi.fi/en/identity-card",
    "https://poliisi.fi/en/how-to-apply-for-an-identity-card",
    "https://poliisi.fi/en/using-your-passport",

    # ── tulli.fi — Finnish Customs ────────────────────────────────────────────
    "https://tulli.fi/en/individuals/moving",
    "https://tulli.fi/en/individuals/moving/to-finland",
    "https://tulli.fi/en/individuals/moving/how-to-declare-removal-goods",
    "https://tulli.fi/en/individuals/moving/goods-imported-by-a-student-arriving-in-finland",
    "https://tulli.fi/en/restrictions/pets",
    "https://tulli.fi/en/restrictions/pets/moving",
    "https://tulli.fi/en/restrictions/pets/travelling",
    "https://tulli.fi/en/restrictions/cars/moving",
    "https://tulli.fi/en/individuals/going-to-order-goods-from-abroad",

    # ── traficom.fi — driving licences and vehicle registration ───────────────
    # Driving licences moved from the Police to Traficom, so poliisi.fi does not
    # answer licence-exchange questions and this domain is the only source that does.
    "https://www.traficom.fi/en/drivers-and-vehicles",
    "https://www.traficom.fi/en/drivers-and-vehicles/driving-licenses",
    "https://www.traficom.fi/en/drivers-and-vehicles/driving-licenses/order-new-driving-licence",
    "https://www.traficom.fi/en/drivers-and-vehicles/driving-licenses/renew-your-driving-licence",
    "https://www.traficom.fi/en/drivers-and-vehicles/vehicle-registration",
    "https://www.traficom.fi/en/drivers-and-vehicles/buying-and-selling-vehicle/importing-vehicle-finland",
    "https://www.traficom.fi/en/drivers-and-vehicles/vehicle-taxation",
    "https://www.traficom.fi/en/drivers-and-vehicles/vehicle-inspection",

    # ── tyosuojelu.fi — occupational safety and worker rights ─────────────────
    "https://www.tyosuojelu.fi/en/employment-relationship",
    "https://www.tyosuojelu.fi/en/employment-relationship/working-hours",
    "https://www.tyosuojelu.fi/en/employment-relationship/employment-contract",
    "https://www.tyosuojelu.fi/en/employment-relationship/pay",
    "https://www.tyosuojelu.fi/en/employment-relationship/termination",
    "https://www.tyosuojelu.fi/en/employment-relationship/rights-and-responsibilities-at-work",
    "https://www.tyosuojelu.fi/en/working-conditions",
    "https://www.tyosuojelu.fi/en/occupational-health",
]
