"""Service-layer boundaries for the ERP.

This module intentionally uses lazy imports so app startup stays stable and
service ownership can be made explicit without creating new import cycles.
"""

from datetime import datetime


SERVICE_OWNERSHIP_MAP = [
    {
        "responsibility": "Database startup safety",
        "owner": "database.startup_database",
        "notes": "Authoritative boot, bootstrap, and cloud-restore decision flow.",
    },
    {
        "responsibility": "Persistence, backup, and restore",
        "owner": "database",
        "notes": "Canonical DB path, local/cloud backups, recovery diagnostics, and exports.",
    },
    {
        "responsibility": "Auth, session, and role permissions",
        "owner": "modules role helpers via enterprise_services",
        "notes": "Compatibility wrappers keep current callers stable while centralizing access.",
    },
    {
        "responsibility": "Accounting posting and workflow enforcement",
        "owner": "accounting_engine",
        "notes": "Journal posting, posting-state enforcement, and document workflow diagnostics.",
    },
    {
        "responsibility": "Reporting trust and reconciliation",
        "owner": "accounting_engine",
        "notes": "Journal-driven report integrity, reconciliation, and period-control diagnostics.",
    },
    {
        "responsibility": "AI assistant configuration",
        "owner": "modules.get_openai_client_status via enterprise_services",
        "notes": "One shared OpenAI key/client path with local, non-blocking failures.",
    },
    {
        "responsibility": "System Health operations snapshot",
        "owner": "enterprise_services.build_operations_console_snapshot",
        "notes": "Reusable aggregation layer for admin diagnostics; UI rendering remains in app.py.",
    },
]


def get_service_ownership_map():
    """Return the authoritative service ownership map for admin diagnostics."""
    return list(SERVICE_OWNERSHIP_MAP)


def get_ai_service_status():
    """Return the shared OpenAI client/status through the AI service boundary."""
    from modules import get_openai_client_status

    return get_openai_client_status()


def has_permission(role, permission):
    """Compatibility wrapper for centralized permission checks."""
    from modules import user_has_permission

    return user_has_permission(role, permission)


def require_role_permission(role, permission, action_label=None):
    """Compatibility wrapper that keeps permission enforcement behind one boundary."""
    from modules import require_permission

    return require_permission(role, permission, action_label=action_label)


def _safe_section(label, loader):
    try:
        return loader()
    except Exception as exc:
        return {
            "ok": False,
            "service_section": label,
            "reason": str(exc),
        }


def build_operations_console_snapshot(
    conn=None,
    selected_company_key=None,
    branch_id=None,
    end_date=None,
    audit_limit=25,
):
    """Collect System Health diagnostics without coupling UI code to every service.

    The returned dictionary is intentionally plain data so Streamlit rendering can
    stay in app.py while diagnostics remain reusable and centrally maintained.
    """
    from database import (
        get_audit_operations_summary,
        get_persistence_diagnostics,
        get_schema_manifest_diagnostics,
        run_persistence_self_test,
    )

    snapshot = {
        "service_ownership": get_service_ownership_map(),
        "persistence": _safe_section("persistence", get_persistence_diagnostics),
        "persistence_self_test": _safe_section("persistence_self_test", run_persistence_self_test),
        "schema": None,
        "audit": None,
        "accounting_core": None,
        "document_workflow": None,
        "reporting_trust": None,
    }

    if conn is not None:
        snapshot["schema"] = _safe_section(
            "schema_manifest",
            lambda: get_schema_manifest_diagnostics(conn),
        )
        snapshot["audit"] = _safe_section(
            "audit_operations",
            lambda: get_audit_operations_summary(conn=conn, limit=audit_limit),
        )

    if selected_company_key:
        from accounting_engine import (
            get_document_workflow_diagnostics,
            get_journal_dominance_diagnostics,
            get_reporting_trust_diagnostics,
        )

        report_end_date = end_date or datetime.now().date()
        snapshot["accounting_core"] = _safe_section(
            "accounting_core",
            lambda: get_journal_dominance_diagnostics(
                selected_company_key,
                branch_id=branch_id,
                conn=conn,
            ),
        )
        snapshot["document_workflow"] = _safe_section(
            "document_workflow",
            lambda: get_document_workflow_diagnostics(
                selected_company_key,
                branch_id=branch_id,
                conn=conn,
            ),
        )
        snapshot["reporting_trust"] = _safe_section(
            "reporting_trust",
            lambda: get_reporting_trust_diagnostics(
                selected_company_key,
                end_date=report_end_date,
                branch_id=branch_id,
                conn=conn,
            ),
        )

    return snapshot
