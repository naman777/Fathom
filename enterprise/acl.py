"""Who may read what in the enterprise corpus.

EnterpriseRAG-Bench ships no permissions (documents are doc_id, source_type, title, content), so these rules are
Fathom's own, written to look like a real company's: a document belongs to one or more *groups*, a role is a set of
groups, and a search only returns chunks whose groups intersect the role's. The check is a filter inside the Qdrant
query (enterprise/store.py), so text a role may not read never reaches the reranker or the answer model.

Deny by default: a document that matches no rule gets the "restricted" group, which only the admin role holds. About
2,500 Slack documents have a malformed channel name and land there.
"""

GROUPS = ("all", "eng", "gtm", "product", "people", "finance", "restricted")

# Slack channel -> groups
_SLACK = {
    **{c: ["all"] for c in ("general", "all-hands", "announcements", "random", "lunch-plans", "new-hires", "help", "docs",
                            "sports", "memes", "watercooler")},
    **{c: ["eng"] for c in ("eng", "eng-platform", "eng-runtime", "eng-ml", "eng-releases", "eng-infra", "eng-security",
                            "eng-oncall", "eng-sre", "incidents", "architecture", "devex", "postmortems", "release-war-room")},
    **{c: ["gtm"] for c in ("sales", "customer-success", "partnerships", "marketing", "sales-poc-benchmark")},
    "support": ["eng", "gtm"],
    "product": ["product"], "design": ["product"],
    "people-ops": ["people"],
    "finance": ["finance"], "vendors": ["finance"],
}

# Every non-Slack source maps as a whole: the dataset has no finer signal (no space, project or owner field).
_SOURCE = {
    "confluence": ["all"],          # company wiki
    "google_drive": ["all"],        # shared drive
    "github": ["eng"],
    "linear": ["eng", "product"],
    "jira": ["eng", "gtm"],         # support tickets, internal and customer-facing
    "hubspot": ["gtm"],             # CRM records
    "fireflies": ["gtm"],           # recorded customer calls
    "gmail": ["gtm"],               # customer email threads
}

# role id -> (label shown in the UI, groups; None = unrestricted)
ROLES: dict[str, tuple[str, list[str] | None]] = {
    "engineer": ("Engineer", ["all", "eng", "product"]),
    "sales": ("Sales / Customer Success", ["all", "gtm", "product"]),
    "hr": ("People Ops", ["all", "people"]),
    "finance": ("Finance", ["all", "finance"]),
    "new_hire": ("New hire", ["all"]),
    "admin": ("Admin (sees everything)", None),
}
DEFAULT_ROLE = "new_hire"  # an unknown or missing role gets the least access, never the most


def groups_for(source: str, title: str) -> list[str]:
    if source == "slack":
        return _SLACK.get((title or "").strip(), ["restricted"])
    return _SOURCE.get(source, ["restricted"])


def role_groups(role: str | None) -> list[str] | None:
    """Groups a role may read. None means unrestricted (admin only)."""
    return ROLES.get(role or "", ROLES[DEFAULT_ROLE])[1]


def can_read(role: str | None, doc_groups: list[str]) -> bool:
    allowed = role_groups(role)
    return allowed is None or bool(set(allowed) & set(doc_groups))
