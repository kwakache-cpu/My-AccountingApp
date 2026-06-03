"""Offline PostgreSQL deployment dry-run planner.

Reads generated schema artifacts and produces a phased deployment plan report.
This module does not connect to a database and does not execute SQL.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re


REPO_ROOT = Path(__file__).resolve().parent
DEFAULT_SCHEMA_SQL = REPO_ROOT / "reports" / "postgres_generated_schema.sql"
DEFAULT_VALIDATION_REPORT = REPO_ROOT / "reports" / "postgres_schema_validation_report.md"
DEFAULT_DEPLOYMENT_PLAN = REPO_ROOT / "reports" / "postgres_schema_deployment_plan.md"
DEFAULT_DRY_RUN_REPORT = REPO_ROOT / "reports" / "postgres_deployment_dry_run_plan.md"


PHASE_DEFINITIONS: list[tuple[str, str, list[str]]] = [
    ("Phase 1", "Migration history and system metadata", ["migration_history", "schema_version", "database_identity", "system_settings"]),
    ("Phase 2", "Companies, branches, and users", ["companies", "branch_type_catalog", "branches", "users", "branch_type_module_defaults", "branch_module_grants", "company_subscriptions", "subscription_plan_settings", "license_payment_transactions"]),
    ("Phase 3", "Chart of accounts, customers, and suppliers", ["chart_of_accounts", "customers", "suppliers", "counterparties", "bank_accounts", "customer_transactions", "supplier_transactions"]),
    ("Phase 4", "Inventory", ["inventory", "inventory_import_batches", "stock_movements", "purchase_orders"]),
    ("Phase 5", "Invoices, bills, and payments", ["invoices", "invoice_lines", "bills", "bill_lines", "payments", "payment_allocations", "sales_invoices", "accounts_payable", "vouchers", "transactions", "recurring_transactions", "pending_approvals"]),
    ("Phase 6", "Journal tables", ["journal_entries", "journal_lines", "accounting_periods"]),
    ("Phase 7", "POS", ["pos_sales", "pos_sale_lines", "pos_returns", "pos_suspended_sales", "cashier_closings"]),
    ("Phase 8", "Payroll and fixed assets", ["payroll", "payroll_records", "fixed_assets"]),
    ("Phase 9", "Audit and system tables", ["audit_logs", "system_logs", "migration_logs", "maintenance_settings"]),
]


@dataclass
class TableDependency:
    table: str
    referenced_table: str
    column: str = ""
    referenced_column: str = ""


@dataclass
class DeploymentPhase:
    phase_id: str
    name: str
    tables: list[str]
    missing_tables: list[str] = field(default_factory=list)
    dependencies: list[TableDependency] = field(default_factory=list)
    ordering_risks: list[str] = field(default_factory=list)


@dataclass
class DeploymentDryRunPlan:
    phases: list[DeploymentPhase]
    unassigned_tables: list[str]
    dependency_risks: list[str]
    validation_score: int
    validation_readiness: str
    deployment_readiness_score: int
    deployment_readiness: str
    rollback_strategy: list[str]
    staging_checklist: list[str]


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def parse_generated_tables(schema_sql: str) -> list[str]:
    tables = re.findall(
        r"\bCREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z_][A-Za-z0-9_]*)\b",
        schema_sql,
        flags=re.IGNORECASE,
    )
    return sorted(set(tables))


def _extract_create_table_blocks(schema_sql: str) -> dict[str, str]:
    blocks: dict[str, str] = {}
    pattern = re.compile(
        r"\bCREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z_][A-Za-z0-9_]*)\b(.*?);",
        flags=re.IGNORECASE | re.DOTALL,
    )
    for match in pattern.finditer(schema_sql):
        blocks[match.group(1)] = match.group(0)
    return blocks


def parse_fk_dependencies(schema_sql: str) -> list[TableDependency]:
    dependencies: list[TableDependency] = []
    for table, block in _extract_create_table_blocks(schema_sql).items():
        for fk_match in re.finditer(
            r"FOREIGN\s+KEY\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)\s+REFERENCES\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)",
            block,
            flags=re.IGNORECASE,
        ):
            dependencies.append(
                TableDependency(
                    table=table,
                    column=fk_match.group(1),
                    referenced_table=fk_match.group(2),
                    referenced_column=fk_match.group(3),
                )
            )
    return dependencies


def parse_validation_result(validation_report: str) -> tuple[int, str]:
    score_match = re.search(r"- Score:\s*(\d+)/100", validation_report)
    readiness_match = re.search(r"- Deployment readiness:\s*\*\*([A-Z]+)\*\*", validation_report)
    score = int(score_match.group(1)) if score_match else 0
    readiness = readiness_match.group(1) if readiness_match else "RED"
    return score, readiness


def _phase_lookup(phases: list[DeploymentPhase]) -> dict[str, int]:
    lookup: dict[str, int] = {}
    for index, phase in enumerate(phases):
        for table in phase.tables:
            lookup[table] = index
    return lookup


def build_deployment_phases(tables: list[str], dependencies: list[TableDependency]) -> list[DeploymentPhase]:
    table_set = set(tables)
    phases: list[DeploymentPhase] = []
    for phase_id, name, phase_tables in PHASE_DEFINITIONS:
        present = [table for table in phase_tables if table in table_set]
        missing = [table for table in phase_tables if table not in table_set]
        phase_dependencies = [dependency for dependency in dependencies if dependency.table in present]
        phases.append(
            DeploymentPhase(
                phase_id=phase_id,
                name=name,
                tables=present,
                missing_tables=missing,
                dependencies=phase_dependencies,
            )
        )

    lookup = _phase_lookup(phases)
    for phase_index, phase in enumerate(phases):
        for dependency in phase.dependencies:
            parent_phase_index = lookup.get(dependency.referenced_table)
            if parent_phase_index is None:
                phase.ordering_risks.append(
                    f"{dependency.table}.{dependency.column} references missing table {dependency.referenced_table}.{dependency.referenced_column}"
                )
            elif parent_phase_index > phase_index:
                parent_phase = phases[parent_phase_index].phase_id
                phase.ordering_risks.append(
                    f"{dependency.table}.{dependency.column} references {dependency.referenced_table}.{dependency.referenced_column} in later {parent_phase}"
                )
    return phases


def _build_dependency_risks(phases: list[DeploymentPhase]) -> list[str]:
    risks: list[str] = []
    for phase in phases:
        for risk in phase.ordering_risks:
            risks.append(f"{phase.phase_id}: {risk}")
        for missing in phase.missing_tables:
            risks.append(f"{phase.phase_id}: planned table not found in generated SQL: {missing}")
    return sorted(risks)


def _score_readiness(validation_score: int, validation_readiness: str, dependency_risks: list[str], unassigned_tables: list[str]) -> tuple[int, str]:
    score = validation_score
    score -= min(len(dependency_risks) * 5, 35)
    score -= min(len(unassigned_tables) * 3, 20)
    if validation_readiness == "RED":
        score -= 25
    elif validation_readiness == "YELLOW":
        score -= 5
    score = max(score, 0)

    if dependency_risks or validation_readiness == "RED":
        readiness = "RED"
    elif validation_readiness == "YELLOW" or unassigned_tables:
        readiness = "YELLOW"
    else:
        readiness = "GREEN"
    return score, readiness


def build_rollback_strategy() -> list[str]:
    return [
        "Use a staging-only database clone or disposable schema before any future execution.",
        "Wrap future deployer phases in explicit transactions where PostgreSQL permits it.",
        "Record every applied phase in a PostgreSQL migration history table before moving to the next phase.",
        "On failure, stop immediately and drop only the staging schema or objects created by the failed dry-run phase.",
        "Do not roll back or mutate production SQLite data as part of PostgreSQL deployment recovery.",
        "Capture generated SQL, validation report, deployment logs, and table-count validation output for audit review.",
    ]


def build_staging_checklist() -> list[str]:
    return [
        "Confirm PostgreSQL runtime remains disabled until schema validation and deployer review pass.",
        "Review all generated SQL manually, especially type conversions and timestamp/date columns.",
        "Replace captured index placeholders with explicit PostgreSQL CREATE INDEX statements.",
        "Review FK ordering risks and decide whether to add foreign keys after base table creation.",
        "Prepare migration history and seed-data strategy before any staging execution.",
        "Run the schema validator after any generated SQL change.",
        "Require a staging-only approval before any future schema deployment command exists.",
    ]


def build_dry_run_plan(schema_sql: str, validation_report: str, deployment_plan_text: str = "") -> DeploymentDryRunPlan:
    tables = parse_generated_tables(schema_sql)
    dependencies = parse_fk_dependencies(schema_sql)
    phases = build_deployment_phases(tables, dependencies)
    assigned_tables = {table for phase in phases for table in phase.tables}
    unassigned_tables = sorted(set(tables) - assigned_tables)
    dependency_risks = _build_dependency_risks(phases)
    validation_score, validation_readiness = parse_validation_result(validation_report)
    readiness_score, readiness = _score_readiness(
        validation_score=validation_score,
        validation_readiness=validation_readiness,
        dependency_risks=dependency_risks,
        unassigned_tables=unassigned_tables,
    )
    if deployment_plan_text and "schema deployment is still not implemented" in deployment_plan_text:
        readiness = "RED" if dependency_risks else readiness
    return DeploymentDryRunPlan(
        phases=phases,
        unassigned_tables=unassigned_tables,
        dependency_risks=dependency_risks,
        validation_score=validation_score,
        validation_readiness=validation_readiness,
        deployment_readiness_score=readiness_score,
        deployment_readiness=readiness,
        rollback_strategy=build_rollback_strategy(),
        staging_checklist=build_staging_checklist(),
    )


def render_dry_run_report(plan: DeploymentDryRunPlan) -> str:
    lines = [
        "# PostgreSQL Deployment Dry-Run Plan",
        "",
        "Phase: 5B.13G",
        "",
        "Generated offline from PostgreSQL schema artifacts. No SQL execution, PostgreSQL connection, Supabase call, runtime enablement, or data migration was attempted.",
        "",
        "## Readiness",
        "",
        f"- Deployment readiness score: {plan.deployment_readiness_score}/100",
        f"- Deployment readiness: **{plan.deployment_readiness}**",
        f"- Source schema validation score: {plan.validation_score}/100",
        f"- Source schema validation readiness: {plan.validation_readiness}",
        "",
        "## Deployment Order",
        "",
    ]
    for phase in plan.phases:
        lines.extend([f"### {phase.phase_id}: {phase.name}", ""])
        if phase.tables:
            lines.extend(f"- {table}" for table in phase.tables)
        else:
            lines.append("- No generated tables assigned.")
        if phase.dependencies:
            lines.extend(["", "Dependencies:"])
            lines.extend(
                f"- {dependency.table}.{dependency.column} -> {dependency.referenced_table}.{dependency.referenced_column}"
                for dependency in phase.dependencies
            )
        if phase.ordering_risks:
            lines.extend(["", "Ordering risks:"])
            lines.extend(f"- {risk}" for risk in phase.ordering_risks)
        lines.append("")

    lines.extend(["## FK Dependency Risks", ""])
    if plan.dependency_risks:
        lines.extend(f"- {risk}" for risk in plan.dependency_risks)
    else:
        lines.append("- None detected for the proposed phase order.")

    lines.extend(["", "## Unassigned Generated Tables", ""])
    if plan.unassigned_tables:
        lines.extend(f"- {table}" for table in plan.unassigned_tables)
    else:
        lines.append("- None.")

    lines.extend(["", "## Rollback Planning", ""])
    lines.extend(f"- {item}" for item in plan.rollback_strategy)

    lines.extend(["", "## Staging-Only Deployment Checklist", ""])
    lines.extend(f"- {item}" for item in plan.staging_checklist)

    lines.extend(
        [
            "",
            "## Remaining Blockers",
            "",
            "- PostgreSQL schema deployment is not implemented.",
            "- Generated SQL still requires manual review before it can be executed in staging.",
            "- Captured index placeholders must be replaced with real PostgreSQL index definitions.",
            "- Seed data, migration history writes, and validation queries still need a staging-only deployer design.",
            "- Runtime cutover remains NO-GO until deployment, data migration, and application SQL portability are complete.",
            "",
        ]
    )
    return "\n".join(lines)


def generate_postgres_deployment_dry_run_plan(
    schema_sql_path: Path = DEFAULT_SCHEMA_SQL,
    validation_report_path: Path = DEFAULT_VALIDATION_REPORT,
    deployment_plan_path: Path = DEFAULT_DEPLOYMENT_PLAN,
    output_path: Path = DEFAULT_DRY_RUN_REPORT,
) -> DeploymentDryRunPlan:
    schema_sql = _read_text(schema_sql_path)
    validation_report = _read_text(validation_report_path)
    deployment_plan_text = _read_text(deployment_plan_path)
    plan = build_dry_run_plan(schema_sql, validation_report, deployment_plan_text)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_dry_run_report(plan), encoding="utf-8")
    return plan


if __name__ == "__main__":
    generated_plan = generate_postgres_deployment_dry_run_plan()
    print(
        "Generated PostgreSQL deployment dry-run plan: "
        f"score={generated_plan.deployment_readiness_score}/100 "
        f"readiness={generated_plan.deployment_readiness} "
        f"phases={len(generated_plan.phases)} "
        f"risks={len(generated_plan.dependency_risks)}"
    )
