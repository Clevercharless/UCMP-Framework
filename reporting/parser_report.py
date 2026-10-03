"""
reporting.parser_report
=========================
Parser Report: what the Parser Engine (Module 5) found in the source
repository - notebook inventory by category/language, Azure construct
counts, and the business objects (tables, shared functions) that will be
preserved untouched.
"""

from __future__ import annotations

from typing import Dict

from reporting.markdown_utils import bullet_list, heading, kv_block, table


def build_parser_report(knowledge_model: Dict) -> str:
    metadata = knowledge_model["notebook_metadata"]
    constructs = knowledge_model["azure_constructs"]
    business_objects = knowledge_model["business_objects"]

    by_category: Dict[str, int] = {}
    by_language: Dict[str, int] = {}
    for nb in metadata:
        by_category[nb["category"]] = by_category.get(nb["category"], 0) + 1
        by_language[nb["language"]] = by_language.get(nb["language"], 0) + 1

    lines = [
        heading("Parser Report", 1),
        kv_block([
            ("Repository", knowledge_model["repo_name"]),
            ("Notebooks parsed", len(metadata)),
            ("Unique Azure constructs found", len(constructs)),
            ("Business objects preserved", len(business_objects)),
            ("Changed notebooks", sum(1 for nb in metadata if nb.get("migration_classification") == "CHANGED")),
            ("Notebooks requiring review", sum(1 for nb in metadata if nb.get("review_required"))),
        ]),
        "",
        heading("Notebooks by Category", 2),
        table(["Category", "Count"], sorted(by_category.items())),
        "",
        heading("Notebooks by Language", 2),
        table(["Language", "Count"], sorted(by_language.items())),
        "",
        heading("Notebook Inventory", 2),
        table(
            ["Path", "Category", "Language", "Cells", "Azure Constructs", "Classification", "Review", "Parse Error"],
            [
                [nb["relative_path"], nb["category"], nb["language"], nb["cell_count"],
                 nb["azure_construct_count"], nb.get("migration_classification", "NO_CHANGE"),
                 "YES" if nb.get("review_required") else "no", nb["parse_error"] or "-"]
                for nb in metadata
            ],
        ),
        "",
        heading("Azure Constructs Found (by type)", 2),
        table(
            ["Construct Type", "Value", "Occurrences", "Found In"],
            [
                [c["construct_type"], c["value"], c["occurrences"], ", ".join(c["found_in"])]
                for c in constructs
            ],
        ),
        "",
        heading("Business Objects Preserved (untouched)", 2),
        bullet_list(
            f"[{b['type']}] {b['name']}"
            + (f" (defined in {b['defined_in']})" if b["type"] == "shared_function" else
               f" (referenced in {len(b['referenced_in'])} notebook(s))")
            for b in business_objects
        ),
    ]
    return "\n".join(lines)
