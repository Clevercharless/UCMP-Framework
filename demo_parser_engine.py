"""
demo_parser_engine.py
=======================
Standalone demo for Module 5 (Parser Engine), integrated with Modules 1-4
(Orchestrator, Configuration Manager, Authentication Manager, Repository
Manager).

Pipeline order demonstrated:
    ConfigurationManager -> AuthenticationManager -> RepositoryManager ->
    ParserEngine

Runs against the real ucmp-demo/Loan-Platform repo (16 notebooks) and
prints a summary of the generated MigrationKnowledgeModel.json.

Run with:
    python demo_parser_engine.py
"""

from __future__ import annotations

import os

from auth.auth_manager import AuthenticationManager
from config.config_manager import ConfigurationManager
from orchestrator.context import PipelineContext
from orchestrator.orchestrator import Orchestrator
from parser.parser_engine import ParserEngine
from repository.repository_manager import RepositoryManager


def build_demo_pipeline(config_path: str | None) -> Orchestrator:
    config_manager = ConfigurationManager(config_path=config_path)
    auth_manager = AuthenticationManager()
    repository_manager = RepositoryManager(token_store=auth_manager.token_store)
    parser_engine = ParserEngine()

    stages = [config_manager, auth_manager, repository_manager, parser_engine]
    return Orchestrator(stages=stages, fail_fast=True)


def main() -> None:
    sample_config_path = os.path.normpath(
        os.path.join(os.path.dirname(__file__), "..", "ucmp-demo", "docs", "sample_config.yaml")
    )
    config_path = sample_config_path if os.path.exists(sample_config_path) else None

    orchestrator = build_demo_pipeline(config_path)
    context = orchestrator.run(PipelineContext())

    print("\n=== Pipeline Summary ===")
    for entry in context.summary()["stages"]:
        print(f"  {entry['stage_name']:<28} {entry['status']:<10} {entry['duration_seconds']}s")
    print(f"\nOverall status: {context.summary()['overall_status']}")

    model = context.get_artifact("knowledge_model")
    graph_summary = model["dependencies"]["graph_summary"]

    print(f"\nKnowledge model written to: {context.metadata.get('knowledge_model_path')}")

    print("\n=== Dependency Graph ===")
    print(f"  nodes:       {graph_summary['node_count']}")
    print(f"  edges:       {graph_summary['edge_count']}")
    print(f"  acyclic:     {graph_summary['is_acyclic']}")
    print("  topological execution order:")
    for i, nb in enumerate(graph_summary["topological_order"], start=1):
        print(f"    {i:>2}. {nb}")

    print(f"\n=== Azure Constructs Found: {len(model['azure_constructs'])} ===")
    by_type: dict[str, int] = {}
    for c in model["azure_constructs"]:
        by_type[c["construct_type"]] = by_type.get(c["construct_type"], 0) + 1
    for construct_type, count in sorted(by_type.items()):
        print(f"  {construct_type:<20} {count} unique value(s)")

    print(f"\n=== Configuration References: {len(model['configuration_references'])} ===")
    for ref in model["configuration_references"]:
        print(f"  [{ref['reference_type']}] {ref['value']} (x{ref['occurrences']})")

    print(f"\n=== Transformation Candidates: {len(model['transformation_candidates'])} ===")
    by_rule_category: dict[str, int] = {}
    for tc in model["transformation_candidates"]:
        by_rule_category[tc["rule_category_hint"]] = by_rule_category.get(tc["rule_category_hint"], 0) + 1
    for rule_category, count in sorted(by_rule_category.items()):
        print(f"  {rule_category:<20} {count} candidate(s) -> future Rule Repository lookup")

    tables = [b for b in model["business_objects"] if b["type"] == "table"]
    functions = [b for b in model["business_objects"] if b["type"] == "shared_function"]
    print(f"\n=== Business Objects: {len(tables)} table(s), {len(functions)} shared function(s) ===")
    for t in tables:
        print(f"  [table] {t['name']}")
    for f in functions:
        print(f"  [function] {f['name']} (defined in {f['defined_in']})")

    print(f"\n=== Manual Review Items: {len(model['manual_review_items'])} ===")
    for item in model["manual_review_items"]:
        print(f"  [{item['notebook']}] {item['reason']}")
        print(f"      detail: {item['detail']}")


if __name__ == "__main__":
    main()
