"""Centralized registry of Indian official legal/regulatory sources.

Every regulatory search result is classified against this single allowlist —
adding a new official domain here automatically upgrades matching results to
"official" everywhere (search bias, classification, and the frontend badge).
Anything not in this list is treated as a third-party source and is never
presented as official.
"""

from urllib.parse import urlparse

# Domain -> canonical authority name. Subdomains of a listed domain are treated
# as the same official source (e.g. regulator.fssai.gov.in -> FSSAI).
INDIAN_OFFICIAL_SOURCES: dict[str, str] = {
    "indiacode.nic.in": "India Code (NIC, Government of India)",
    "egazette.gov.in": "eGazette, Gazette of India (Government of India)",
    "fssai.gov.in": "Food Safety and Standards Authority of India (FSSAI)",
    "rbi.org.in": "Reserve Bank of India (RBI)",
    "sebi.gov.in": "Securities and Exchange Board of India (SEBI)",
    "mca.gov.in": "Ministry of Corporate Affairs (MCA)",
    "incometax.gov.in": "Income Tax Department, Government of India",
    "gst.gov.in": "Goods and Services Tax Network (GSTN)",
    "meity.gov.in": "Ministry of Electronics & IT (MeitY)",
    "labour.gov.in": "Ministry of Labour & Employment, Government of India",
}

Basis = tuple[bool, str, str | None]
# (official_source, source_type, authority)
SOURCE_TYPE_OFFICIAL = "official"
SOURCE_TYPE_THIRD_PARTY = "third_party"


def official_authority_for_host(host: str) -> str | None:
    """Returns the canonical authority for an official domain, or None for
    unknown/third-party hosts."""
    host = (host or "").lower().partition(":")[0]  # strip any port
    for domain, authority in INDIAN_OFFICIAL_SOURCES.items():
        if host == domain or host.endswith(f".{domain}"):
            return authority
    return None


def classify_source(url: str | None) -> Basis:
    """Classifies a source URL against the official-domain allowlist.

    Returns (official_source, source_type, authority). A missing or unparsable
    URL is treated as third-party with no authority.
    """
    if not url:
        return (False, SOURCE_TYPE_THIRD_PARTY, None)
    try:
        host = urlparse(url).netloc
    except ValueError:
        return (False, SOURCE_TYPE_THIRD_PARTY, None)
    authority = official_authority_for_host(host)
    if authority:
        return (True, SOURCE_TYPE_OFFICIAL, authority)
    return (False, SOURCE_TYPE_THIRD_PARTY, None)


def official_domains() -> list[str]:
    """The allowlist domains, used to bias discovery towards official sources."""
    return list(INDIAN_OFFICIAL_SOURCES.keys())