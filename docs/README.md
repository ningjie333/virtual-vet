# Docs Index

This folder now separates current reference docs from archived working notes.

## Start Here

Recommended first-pass reading order:

1. [../README.md](../README.md)
2. [architecture.md](architecture.md)
3. [kernel-first-design.md](kernel-first-design.md)
4. [kernel-time-architecture-sketch.md](kernel-time-architecture-sketch.md)
5. [test-command-guide.md](test-command-guide.md)

## Core Architecture

- [architecture.md](architecture.md): concise authoritative rules for layering, time semantics, solver status, and testing tiers
- [architecture-improvement-plan.md](architecture-improvement-plan.md): issues found during xfail cleanup (2026-06-27) and prioritized fix plan
- [kernel-first-design.md](kernel-first-design.md): integrated design narrative joining kernel-first positioning, time semantics, encounter-state construction, runtime ownership, and testing strategy
- [kernel-time-architecture-sketch.md](kernel-time-architecture-sketch.md): time-design sketch for physical time, encounter time, natural history, and initialization strategy
- [presentation-state-builder-sketch.md](presentation-state-builder-sketch.md): sketch for replacing raw warmup replay with kernel-adjacent encounter-state construction

## Testing

- [harness-engineering.md](harness-engineering.md): repeatable validation profiles for API, app, frontend, and core confidence *(待补全)*
- [test-command-guide.md](test-command-guide.md): first choice if you just want to know what test command to run right now *(待补全)*
- [testing.md](testing.md): testing policy, lane semantics, and why the suite is split this way *(待补全)*
- [test-runbook.md](test-runbook.md): detailed timing inventory, bundle list, and hotspot ledger *(待补全)*
- [test-manifest-summary.md](test-manifest-summary.md): generated lane/bundle ownership from `tests/test_manifest.json`
- [heavy-test-triage.md](heavy-test-triage.md): classification of long-running tests into hard validation, engineering regression, observation-only, and rewrite candidates *(待补全)*
- [test-constraint-audit.md](test-constraint-audit.md): strength audit of the current suite, including which tests have real alarm value and which passed tests are weak or misleading
- [test-coverage-effectiveness-report.md](test-coverage-effectiveness-report.md): runtime code-coverage + effectiveness assessment combining pytest-cov collection (fast/core/heavy lanes) with the static constraint-audit ratings (2026-06-27)
- [literature-backed-testing-plan.md](literature-backed-testing-plan.md): map of which kernel tests should be anchored to external veterinary literature and how to tighten them safely *(待补全)*
- [test-evidence-registry.md](test-evidence-registry.md): auditable registry of external evidence sources, target tests, encoding status, and known discrepancies *(待补全)*

## Interpretation / Runtime

- [clinical-interpretation-layer.md](clinical-interpretation-layer.md): interface sketch for reports, signs, phase, and clinical summaries
- [clinical-translation-implementation-audit.md](clinical-translation-implementation-audit.md): current-code audit of the real kernel -> signs -> report path, including duplicated and inconsistent clue definitions
- [clinical-translation-convergence-plan.md](clinical-translation-convergence-plan.md): minimal-change plan for converging signs, reports, and summaries onto one cleaner clinical translation path
- [clue-trigger-plan.md](clue-trigger-plan.md): ownership, taxonomy, migration waves, and validation rules for clue production and diagnosis consumption
- [interpretation-lifecycle-sketch.md](interpretation-lifecycle-sketch.md): current vs target ownership of interpretation object creation and refresh
- [runtime-composition-sketch.md](runtime-composition-sketch.md): target outer runtime shape for advancer, interpreter, and refresh coordination
- [interpretation-refresh-contract.md](interpretation-refresh-contract.md): explicit freshness contract after physical time advancement
- [interpretation-migration-sequence.md](interpretation-migration-sequence.md): recommended order for refresh, outer ownership, and final kernel cleanup

## Archive

- [archive/README.md](archive/README.md): historical audits, repair notes, and superseded design material

If an archived file conflicts with `../README.md` or [architecture.md](architecture.md), prefer the newer documents.
