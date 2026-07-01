"""Service-layer boundaries for the ERP.

This module intentionally uses lazy imports so app startup stays stable and
service ownership can be made explicit without creating new import cycles.
"""

import time
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
        "owner": "modules.get_ai_client_status via enterprise_services",
        "notes": "One shared AI provider path with OpenAI primary and optional Gemini fallback.",
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
    """Return the shared AI provider status through the AI service boundary."""
    from modules import get_ai_client_status

    return get_ai_client_status()


def has_permission(role, permission):
    """Compatibility wrapper for centralized permission checks."""
    from modules import user_has_permission

    return user_has_permission(role, permission)


def require_role_permission(role, permission, action_label=None, company_key=None, conn=None, branch_id=None):
    """Compatibility wrapper that keeps permission enforcement behind one boundary."""
    from modules import require_permission

    return require_permission(
        role,
        permission,
        action_label=action_label,
        company_key=company_key,
        conn=conn,
        branch_id=branch_id,
    )


def _safe_section(label, loader):
    try:
        return loader()
    except Exception as exc:
        return {
            "ok": False,
            "service_section": label,
            "reason": str(exc),
        }


def _timed_section(label, loader, timings_ms):
    started = time.perf_counter()
    try:
        return loader()
    except Exception as exc:
        return {
            "ok": False,
            "service_section": label,
            "reason": str(exc),
        }
    finally:
        timings_ms[label] = round((time.perf_counter() - started) * 1000.0, 2)


def build_operations_console_snapshot(
    conn=None,
    selected_company_key=None,
    branch_id=None,
    end_date=None,
    audit_limit=25,
    audit_mode="fast",
):
    """Collect System Health diagnostics without coupling UI code to every service.

    Fast mode (default) avoids cloud downloads, SQLite file scans, and per-table
  column introspection. Full audit runs only on demand.
    """
    from database import diagnostics_ttl_cache, get_active_db_backend, get_diagnostics_cache_stats

    normalized_mode = str(audit_mode or "fast").strip().lower()
    if normalized_mode not in {"fast", "full"}:
        normalized_mode = "fast"
    cache_key = (
        f"ops_console:{normalized_mode}:{get_active_db_backend()}:"
        f"{selected_company_key or 'none'}:{branch_id or 'none'}:{audit_limit}"
    )
    started = time.perf_counter()
    stats_before = get_diagnostics_cache_stats()
    result = diagnostics_ttl_cache(
        cache_key,
        60,
        lambda: _build_operations_console_snapshot(
            conn=conn,
            selected_company_key=selected_company_key,
            branch_id=branch_id,
            end_date=end_date,
            audit_limit=audit_limit,
            audit_mode=normalized_mode,
        ),
    )
    stats_after = get_diagnostics_cache_stats()
    from_cache = stats_after.get("hits", 0) > stats_before.get("hits", 0)
    try:
        import modules as eka_modules

        eka_modules.record_lv003_hot_path_call(
            "enterprise_services.build_operations_console_snapshot",
            (time.perf_counter() - started) * 1000.0,
            from_cache=from_cache,
            required=normalized_mode == "full",
            recommendation="defer" if normalized_mode == "fast" else "keep",
            surface="system_health",
            metadata={"audit_mode": normalized_mode},
        )
    except Exception:
        pass
    return result


def build_operations_console_full_audit(
    conn=None,
    selected_company_key=None,
    branch_id=None,
    end_date=None,
    audit_limit=25,
):
    """Run the full System Health audit (network/file-heavy checks) on demand."""
    return build_operations_console_snapshot(
        conn=conn,
        selected_company_key=selected_company_key,
        branch_id=branch_id,
        end_date=end_date,
        audit_limit=audit_limit,
        audit_mode="full",
    )


def _get_fast_startup_snapshot():
    """Use process/session cached canonical startup result when available."""
    try:
        import modules as eka_modules

        process_warmup = eka_modules.get_process_warmup_diagnostics()
        process_startup = process_warmup.get("startup_result")
        if isinstance(process_startup, dict) and process_startup.get("startup_ok"):
            return {
                "fast_snapshot": True,
                "from_process_cache": True,
                "configured_backend": process_startup.get("configured_backend"),
                "active_backend": process_startup.get("active_backend"),
                "startup_route": process_startup.get("startup_route"),
                "sqlite_startup_skipped": process_startup.get("sqlite_startup_skipped"),
                "runtime_enabled": process_startup.get("runtime_enabled"),
                "environment": process_startup.get("environment"),
                "production_approved": process_startup.get("production_approved"),
                "postgres_connection_ok": process_startup.get("postgres_connection_ok"),
                "startup_ok": process_startup.get("startup_ok"),
                "elapsed_ms": process_startup.get("elapsed_ms"),
            }
        if eka_modules.st is not None:
            cached = eka_modules.st.session_state.get("canonical_startup_result")
            if isinstance(cached, dict) and cached.get("startup_ok"):
                return {
                    "fast_snapshot": True,
                    "from_session_cache": True,
                    "configured_backend": cached.get("configured_backend"),
                    "active_backend": cached.get("active_backend"),
                    "startup_route": cached.get("startup_route"),
                    "sqlite_startup_skipped": cached.get("sqlite_startup_skipped"),
                    "runtime_enabled": cached.get("runtime_enabled"),
                    "environment": cached.get("environment"),
                    "production_approved": cached.get("production_approved"),
                    "postgres_connection_ok": cached.get("postgres_connection_ok"),
                    "startup_ok": cached.get("startup_ok"),
                    "elapsed_ms": cached.get("elapsed_ms"),
                }
    except Exception:
        pass
    return {
        "fast_snapshot": True,
        "from_session_cache": False,
        "reason": "startup_result_not_in_session",
    }


def _build_operations_console_snapshot(
    conn=None,
    selected_company_key=None,
    branch_id=None,
    end_date=None,
    audit_limit=25,
    audit_mode="fast",
):
    from database import (
        build_fast_runtime_ping,
        get_audit_operations_summary,
        get_data_migration_export_plan,
        get_data_migration_export_plan_summary,
        get_persistence_diagnostics,
        get_persistence_diagnostics_fast,
        get_postgres_readiness_diagnostics,
        get_recovery_source_diagnostics,
        get_schema_manifest_diagnostics,
        get_startup_backend_diagnostics,
        run_persistence_self_test,
        run_persistence_self_test_fast,
        validate_postgres_runtime_cutover_guard,
    )

    timings_ms = {}
    fast_mode = audit_mode == "fast"
    snapshot = {
        "audit_mode": audit_mode,
        "fast_snapshot": fast_mode,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "timings_ms": timings_ms,
        "service_ownership": get_service_ownership_map(),
        "persistence": None,
        "persistence_self_test": None,
        "paystack": None,
        "subscription_billing": None,
        "schema": None,
        "audit": None,
        "accounting_core": None,
        "document_workflow": None,
        "reporting_trust": None,
        "posting_engine": None,
        "postgres_readiness": None,
        "data_migration_plan": None,
        "startup_backend": None,
        "recovery_source": None,
        "cutover_guard": None,
    }

    runtime_ping = build_fast_runtime_ping(conn) if fast_mode and conn is not None else None

    if fast_mode:
        snapshot["startup_backend"] = _get_fast_startup_snapshot()
        snapshot["persistence"] = _timed_section(
            "persistence_diagnostics",
            lambda: get_persistence_diagnostics_fast(conn=conn, runtime_ping=runtime_ping),
            timings_ms,
        )
        snapshot["persistence_self_test"] = _timed_section(
            "persistence_self_test",
            lambda: run_persistence_self_test_fast(conn=conn, runtime_ping=runtime_ping),
            timings_ms,
        )
        snapshot["postgres_readiness"] = {
            "fast_snapshot": True,
            "checked": False,
            "reason": "not_checked_in_fast_mode",
        }
        snapshot["data_migration_plan"] = {
            "fast_snapshot": True,
            "checked": False,
            "reason": "not_checked_in_fast_mode",
        }
        snapshot["recovery_source"] = {
            "fast_snapshot": True,
            "checked": False,
            "reason": "not_checked_in_fast_mode",
        }
        snapshot["cutover_guard"] = {
            "fast_snapshot": True,
            "checked": False,
            "reason": "not_checked_in_fast_mode",
        }
        snapshot["subscription_billing"] = {
            "fast_snapshot": True,
            "checked": False,
            "reason": "not_checked_in_fast_mode",
        }
    else:
        snapshot["persistence"] = _timed_section("persistence_diagnostics", get_persistence_diagnostics, timings_ms)
        snapshot["persistence_self_test"] = _timed_section("persistence_self_test", run_persistence_self_test, timings_ms)
        snapshot["postgres_readiness"] = _timed_section(
            "postgres_readiness",
            lambda: get_postgres_readiness_diagnostics(conn=conn, include_table_introspection=False),
            timings_ms,
        )
        snapshot["data_migration_plan"] = _timed_section(
            "data_migration_plan",
            lambda: get_data_migration_export_plan(conn=conn, include_row_counts=True, include_columns=True),
            timings_ms,
        )
        snapshot["startup_backend"] = _timed_section("startup_backend_diagnostics", get_startup_backend_diagnostics, timings_ms)
        snapshot["recovery_source"] = _timed_section("recovery_source_diagnostics", get_recovery_source_diagnostics, timings_ms)
        snapshot["cutover_guard"] = _timed_section("cutover_guard", validate_postgres_runtime_cutover_guard, timings_ms)
        if conn is not None:
            snapshot["schema"] = _timed_section(
                "schema_manifest",
                lambda: get_schema_manifest_diagnostics(conn),
                timings_ms,
            )
            snapshot["audit"] = _timed_section(
                "audit_operations",
                lambda: get_audit_operations_summary(conn=conn, limit=audit_limit),
                timings_ms,
            )

        from modules import get_subscription_billing_health_snapshot

        snapshot["subscription_billing"] = _timed_section(
            "subscription_billing",
            get_subscription_billing_health_snapshot,
            timings_ms,
        )

    from modules import get_paystack_diagnostics

    snapshot["paystack"] = _timed_section("paystack", get_paystack_diagnostics, timings_ms)

    if selected_company_key and not fast_mode:
        from accounting_engine import (
            get_document_workflow_diagnostics,
            get_journal_dominance_diagnostics,
            get_reporting_trust_diagnostics,
            get_unified_posting_engine_diagnostics,
        )

        report_end_date = end_date or datetime.now().date()
        snapshot["accounting_core"] = _timed_section(
            "accounting_core",
            lambda: get_journal_dominance_diagnostics(
                selected_company_key,
                branch_id=branch_id,
                conn=conn,
            ),
            timings_ms,
        )
        snapshot["document_workflow"] = _timed_section(
            "document_workflow",
            lambda: get_document_workflow_diagnostics(
                selected_company_key,
                branch_id=branch_id,
                conn=conn,
            ),
            timings_ms,
        )
        snapshot["reporting_trust"] = _timed_section(
            "reporting_trust",
            lambda: get_reporting_trust_diagnostics(
                selected_company_key,
                end_date=report_end_date,
                branch_id=branch_id,
                conn=conn,
            ),
            timings_ms,
        )
        snapshot["posting_engine"] = _timed_section(
            "posting_engine",
            lambda: get_unified_posting_engine_diagnostics(
                selected_company_key,
                branch_id=branch_id,
                conn=conn,
            ),
            timings_ms,
        )

    snapshot["total_elapsed_ms"] = round(sum(timings_ms.values()), 2)
    snapshot["top_slow_steps"] = sorted(
        [{"step": step, "elapsed_ms": elapsed} for step, elapsed in timings_ms.items()],
        key=lambda item: item["elapsed_ms"],
        reverse=True,
    )[:10]
    return snapshot
