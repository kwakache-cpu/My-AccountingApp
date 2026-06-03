"""Offline post-deployment validation framework for future PostgreSQL staging.

The module defines validation categories, expected inventory, and checklist
stages. It reads existing report artifacts only and does not connect to any
database or run SQL.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re


REPO_ROOT = Path(__file__).resolve().parent
DEFAULT_SCHEMA_SQL = REPO_ROOT / "reports" / "postgres_generated_schema.sql"
DEFAULT_SCHEMA_VALIDATION_REPORT = REPO_ROOT / "reports" / "postgres_schema_validation_report.md"
DEFAULT_DEPLOYMENT_DRY_RUN_PLAN = REPO_ROOT / "reports" / "postgres_deployment_dry_run_plan.md"
DEFAULT_OUTPUT_REPORT = REPO_ROOT / "reports" / "postgres_postdeploy_validation_plan.md"

VALIDATION_CATEGORIES = (
    "Schema validation",
    "Table validation",
    "Column validation",
    "Index validation",
    "FK validation",
    "Seed data validation",
    "Migration history validation",
    "Runtime readiness validation",
)

EXPECTED_MIGRATION_TABLES = ("migration_history", "schema_version", "database_identity")
EXPECTED_SEED_TABLES = (
    "branch_type_catalog",
    "branch_type_module_defaults",
    "subscription_plan_settings",
    "system_settings",
    "companies",
    "branches",
    "users",
)


@dataclass(frozen=True)
class ValidationCategory:
    name: str
    objective: str
    evidence_sources: tuple[str, ...]


@dataclass(frozen=True)
class ExpectedForeignKey:
    table: str
    column: str
    references_table: str
    references_column: str


@dataclass(frozen=True)
class ValidationChecklistStage:
    stage: str
    name: str
    checks: tuple[str, ...]


@dataclass
class ExpectedInventory:
    tables: list[str]
    indexes: list[str]
    foreign_keys: list[ExpectedForeignKey]
    migration_tables: list[str]
    seed_tables: list[str]


@dataclass
class PostDeployValidationPlan:
    categories: list[ValidationCategory]
    inventory: ExpectedInventory
    checklist_stages: list[ValidationChecklistStage]
    source_schema_score: str = ""
    source_deployment_readiness: str = ""
    notes: list[str] = field(default_factory=list)


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def parse_generated_tables(schema_sql: str) -> list[str]:
    tables = re.findall(
        r"\bCREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z_][A-Za-z0-9_]*)\b",
        schema_sql,
        flags=re.IGNORECASE,
    )
    return sorted(set(tables))


def parse_captured_indexes(schema_sql: str) -> list[str]:
    created = re.findall(r"\bCREATE\s+(?:UNIQUE\s+)?INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z_][A-Za-z0-9_]*)\b", schema_sql, flags=re.IGNORECASE)
    captured = re.findall(r"^-- INDEX\s+([A-Za-z_][A-Za-z0-9_]*)\s+ON\s+", schema_sql, flags=re.MULTILINE)
    return sorted(set(created + captured))


def _extract_create_table_blocks(schema_sql: str) -> dict[str, str]:
    blocks: dict[str, str] = {}
    pattern = re.compile(
        r"\bCREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z_][A-Za-z0-9_]*)\b(.*?);",
        flags=re.IGNORECASE | re.DOTALL,
    )
    for match in pattern.finditer(schema_sql):
        blocks[match.group(1)] = match.group(0)
    return blocks


def parse_expected_foreign_keys(schema_sql: str) -> list[ExpectedForeignKey]:
    foreign_keys: list[ExpectedForeignKey] = []
    for table, block in _extract_create_table_blocks(schema_sql).items():
        for match in re.finditer(
            r"FOREIGN\s+KEY\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)\s+REFERENCES\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)",
            block,
            flags=re.IGNORECASE,
        ):
            foreign_keys.append(
                ExpectedForeignKey(
                    table=table,
                    column=match.group(1),
                    references_table=match.group(2),
                    references_column=match.group(3),
                )
            )
    return sorted(foreign_keys, key=lambda fk: (fk.table, fk.column, fk.references_table, fk.references_column))


def build_validation_categories() -> list[ValidationCategory]:
    return [
        ValidationCategory("Schema validation", "Confirm schema artifact was applied in the intended staging scope.", ("schema deploy log", "table count query output")),
        ValidationCategory("Table validation", "Confirm every expected table exists after deployment.", ("generated schema inventory", "information_schema.tables snapshot")),
        ValidationCategory("Column validation", "Confirm required columns, primary keys, and nullable/default metadata match the generated artifact.", ("generated schema SQL", "information_schema.columns snapshot")),
        ValidationCategory("Index validation", "Confirm all expected PostgreSQL indexes exist after explicit index definitions are added.", ("generated index inventory", "pg_indexes snapshot")),
        ValidationCategory("FK validation", "Confirm foreign key constraints exist and reference expected parent tables/columns.", ("generated FK inventory", "information_schema constraints snapshot")),
        ValidationCategory("Seed data validation", "Confirm required seed tables contain expected baseline rows.", ("seed manifest", "staging row-count snapshot")),
        ValidationCategory("Migration history validation", "Confirm deployment phases are recorded in PostgreSQL migration metadata.", ("migration history table", "deployment log")),
        ValidationCategory("Runtime readiness validation", "Confirm startup gate remains safe until deployment and validation are complete.", ("startup diagnostics", "configuration review")),
    ]


def build_checklist_stages() -> list[ValidationChecklistStage]:
    return [
        ValidationChecklistStage(
            stage="Stage 1",
            name="Schema deployment validation",
            checks=(
                "Confirm all expected tables exist in the staging schema.",
                "Confirm primary keys exist for every generated table.",
                "Confirm expected foreign keys are present or intentionally deferred.",
                "Confirm expected indexes are present after index placeholders are replaced.",
                "Confirm generated schema validation report still has no forbidden SQLite syntax.",
            ),
        ),
        ValidationChecklistStage(
            stage="Stage 2",
            name="Seed deployment validation",
            checks=(
                "Confirm seed tables exist before seed writes are attempted.",
                "Confirm branch type catalog rows are present.",
                "Confirm subscription plan settings rows are present.",
                "Confirm system settings and baseline company/branch/user seed strategy is approved.",
            ),
        ),
        ValidationChecklistStage(
            stage="Stage 3",
            name="Runtime activation validation",
            checks=(
                "Confirm DATABASE_URL is configured only in staging and remains redacted in logs.",
                "Confirm ERP_ENABLE_POSTGRES_RUNTIME remains disabled until schema and seed checks pass.",
                "Confirm startup gate diagnostics show PostgreSQL readiness criteria are satisfied before any relaxation.",
                "Confirm application SQL portability blockers are reviewed before runtime activation.",
            ),
        ),
        ValidationChecklistStage(
            stage="Stage 4",
            name="Cutover validation",
            checks=(
                "Confirm data migration validation has passed.",
                "Confirm accounting, POS, inventory, payroll, and reporting smoke tests pass on staging PostgreSQL.",
                "Confirm rollback plan and production SQLite preservation plan are approved.",
                "Confirm final cutover decision remains NO-GO until deployment, migration, and runtime tests all pass.",
            ),
        ),
    ]


def _parse_schema_validation_summary(report_text: str) -> tuple[str, str]:
    score_match = re.search(r"- Score:\s*([0-9]+/100)", report_text)
    readiness_match = re.search(r"- Deployment readiness:\s*\*\*([A-Z]+)\*\*", report_text)
    return (
        score_match.group(1) if score_match else "unknown",
        readiness_match.group(1) if readiness_match else "unknown",
    )


def build_expected_inventory(schema_sql: str) -> ExpectedInventory:
    tables = parse_generated_tables(schema_sql)
    table_set = set(tables)
    return ExpectedInventory(
        tables=tables,
        indexes=parse_captured_indexes(schema_sql),
        foreign_keys=parse_expected_foreign_keys(schema_sql),
        migration_tables=[table for table in EXPECTED_MIGRATION_TABLES if table in table_set],
        seed_tables=[table for table in EXPECTED_SEED_TABLES if table in table_set],
    )


def build_postdeploy_validation_plan(
    schema_sql: str,
    schema_validation_report: str = "",
    deployment_dry_run_plan: str = "",
) -> PostDeployValidationPlan:
    score, readiness = _parse_schema_validation_summary(schema_validation_report)
    notes: list[str] = []
    if "Deployment readiness: **YELLOW**" in deployment_dry_run_plan:
        notes.append("Deployment dry-run readiness is YELLOW; this framework remains planning-only.")
    return PostDeployValidationPlan(
        categories=build_validation_categories(),
        inventory=build_expected_inventory(schema_sql),
        checklist_stages=build_checklist_stages(),
        source_schema_score=score,
        source_deployment_readiness=readiness,
        notes=notes,
    )


def render_postdeploy_validation_plan(plan: PostDeployValidationPlan) -> str:
    lines = [
        "# PostgreSQL Post-Deployment Validation Plan",
        "",
        "Phase: 5B.13I",
        "",
        "Offline framework definition only. No database connection, SQL execution, schema deployment, PostgreSQL runtime enablement, or data migration was attempted.",
        "",
        "## Source Artifact Summary",
        "",
        f"- Source schema validation score: {plan.source_schema_score}",
        f"- Source deployment readiness: {plan.source_deployment_readiness}",
        f"- Expected tables: {len(plan.inventory.tables)}",
        f"- Expected indexes: {len(plan.inventory.indexes)}",
        f"- Expected FKs: {len(plan.inventory.foreign_keys)}",
        f"- Expected migration tables: {len(plan.inventory.migration_tables)}",
        f"- Expected seed tables: {len(plan.inventory.seed_tables)}",
        "",
        "## Validation Categories",
        "",
    ]
    for category in plan.categories:
        lines.extend(
            [
                f"### {category.name}",
                "",
                f"- Objective: {category.objective}",
                "- Evidence sources: " + ", ".join(category.evidence_sources),
                "",
            ]
        )

    lines.extend(["## Expected Tables", ""])
    lines.extend(f"- {table}" for table in plan.inventory.tables)

    lines.extend(["", "## Expected Indexes", ""])
    lines.extend(f"- {index}" for index in plan.inventory.indexes)
    if not plan.inventory.indexes:
        lines.append("- None captured.")

    lines.extend(["", "## Expected FKs", ""])
    lines.extend(
        f"- {fk.table}.{fk.column} -> {fk.references_table}.{fk.references_column}"
        for fk in plan.inventory.foreign_keys
    )
    if not plan.inventory.foreign_keys:
        lines.append("- None captured.")

    lines.extend(["", "## Expected Migration Tables", ""])
    lines.extend(f"- {table}" for table in plan.inventory.migration_tables)

    lines.extend(["", "## Expected Seed Tables", ""])
    lines.extend(f"- {table}" for table in plan.inventory.seed_tables)

    lines.extend(["", "## Validation Checklists", ""])
    for stage in plan.checklist_stages:
        lines.extend([f"### {stage.stage}: {stage.name}", ""])
        lines.extend(f"- {check}" for check in stage.checks)
        lines.append("")

    lines.extend(["## Notes", ""])
    if plan.notes:
        lines.extend(f"- {note}" for note in plan.notes)
    else:
        lines.append("- Framework generated from offline artifacts.")

    lines.extend(
        [
            "",
            "## Current Limitations",
            "",
            "- PostgreSQL deployment execution is not implemented.",
            "- This framework does not query staging PostgreSQL.",
            "- Seed manifests and migration-history write behavior still need implementation.",
            "- Runtime cutover remains NO-GO.",
            "",
        ]
    )
    return "\n".join(lines)


def generate_postdeploy_validation_plan(
    schema_sql_path: Path = DEFAULT_SCHEMA_SQL,
    schema_validation_report_path: Path = DEFAULT_SCHEMA_VALIDATION_REPORT,
    deployment_dry_run_plan_path: Path = DEFAULT_DEPLOYMENT_DRY_RUN_PLAN,
    output_path: Path = DEFAULT_OUTPUT_REPORT,
) -> PostDeployValidationPlan:
    schema_sql = _read_text(schema_sql_path)
    schema_validation_report = _read_text(schema_validation_report_path)
    deployment_dry_run_plan = _read_text(deployment_dry_run_plan_path)
    plan = build_postdeploy_validation_plan(schema_sql, schema_validation_report, deployment_dry_run_plan)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_postdeploy_validation_plan(plan), encoding="utf-8")
    return plan


if __name__ == "__main__":
    generated = generate_postdeploy_validation_plan()
    print(
        "Generated PostgreSQL post-deployment validation framework: "
        f"categories={len(generated.categories)} "
        f"tables={len(generated.inventory.tables)} "
        f"indexes={len(generated.inventory.indexes)} "
        f"foreign_keys={len(generated.inventory.foreign_keys)}"
    )
