# ROADMAP

UCMP v1 is scoped specifically to **Azure Databricks -> AWS Databricks**
notebook migration. Everything below is intentionally **not implemented**
in this version - each item is documented here as a future direction only,
per the original project scope. None of these should be inferred from, or
built into, the current codebase.

| Enhancement | Why it's deferred |
|---|---|
| **GCP Adapter** | Would require a new source/target platform pair (`google_databricks` or Dataproc), its own auth provider, storage path rules (`gs://`), and repository conventions. Out of scope for v1's Azure->AWS focus. |
| **Snowflake Adapter** | A fundamentally different target platform (not Databricks) - would need its own Parser Engine dialect handling, warehouse/schema mapping rules, and a different Replacement Engine target shape entirely. |
| **Synapse Adapter** | Azure-to-Azure (Databricks -> Synapse) migration is a different problem than cross-cloud migration; would need its own rule categories and validation logic. |
| **Plugin Architecture** | v1's modules are wired together explicitly in `main.py`/demo scripts. A true plugin system (dynamic module discovery, versioned interfaces, third-party rule/parser plugins) is a significant API-design undertaking of its own. |
| **AI-assisted Rule Recommendation** | v1's Rule Repository is fully deterministic and human-authored YAML. Suggesting *new* rules from unmatched constructs (e.g. via an LLM) is a distinct, higher-risk feature requiring its own validation story. |
| **Cloud Knowledge Base** | A persistent, queryable store of known Azure<->AWS/GCP/Snowflake construct mappings across many migrations (vs. v1's static per-run YAML files) implies real storage infrastructure (SQLite/DuckDB-backed) and a versioning model. |
| **Compatibility Engine** | Deeper semantic compatibility checking (e.g. "will this specific Spark version behave identically on both platforms") goes beyond v1's construct-level static analysis into runtime/version-matrix territory. |
| **Policy Engine** | Organization-specific migration policies (e.g. "always flag PII columns for review", "block migrations touching table X") would need a separate rules-about-rules layer distinct from the Rule Repository's construct-mapping focus. |
| **Risk Analyzer** | Scoring migration risk (blast radius, criticality, rollback difficulty) requires business-context inputs v1 has no model for (e.g. which tables are production-critical). |
| **REST APIs** | v1 is a local CLI/library (`main.py`, demo scripts). Exposing the pipeline as a service (auth, multi-request handling, async job status) is a separate productionization effort. |
| **Web UI** | Would sit on top of the REST API above; not meaningful without it. |
| **Multi-Tenant Support** | v1 assumes a single local run for a single repository. Tenant isolation (data, credentials, rule sets per customer) is an infrastructure concern outside this simulation's scope. |
| **Kubernetes Deployment** | v1 deliberately requires no deployment infrastructure at all - everything runs as local Python. Containerized/orchestrated deployment is only relevant once this becomes a real service (see REST APIs, above). |
| **CI/CD Integration** | Wiring UCMP into a real CI/CD pipeline (triggering on repo changes, gating merges on validation status) is a natural next step once the platform is used against real, non-demo repositories - but requires real CI infrastructure v1 doesn't assume. |

## What v1 *does* include, for contrast

To be explicit about the boundary: v1 ships a complete, working, tested
12-module pipeline (Orchestrator, Configuration Manager, Authentication
Manager, Repository Manager, Parser Engine, Rule Repository, Rule Service,
Transformation Planner, Replacement Engine, Validation Engine, Deployment
Engine, Reporting Engine), a realistic 16-notebook demo repository, 18
externalized migration rules across 7 YAML files, a real local git
commit/push simulation, and 7 architecture diagrams - all runnable with a
single `python main.py` command and zero paid cloud accounts. See
`EXECUTION_GUIDE.md` for how to run it.
