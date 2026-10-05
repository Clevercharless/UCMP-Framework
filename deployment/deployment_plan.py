"""
deployment.deployment_plan
=============================
Data model for the Deployment Plan: an ordered list of DeploymentStep
objects (validation gate, git commit, git push, repository
synchronization, AWS Databricks repository update), each with its own
status, rolled up into an overall deployment outcome - DEPLOYED,
DRY_RUN_COMPLETE, or ABORTED.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class DeploymentStep:
    name: str
    status: str  # completed | skipped | aborted
    detail: Dict[str, Any] = field(default_factory=dict)
    notes: Optional[str] = None

    def to_dict(self) -> Dict:
        return {"name": self.name, "status": self.status, "detail": self.detail, "notes": self.notes}


@dataclass
class DeploymentPlan:
    repo_name: str
    deployment_mode: str  # "dry_run" | "full" | "aborted"
    validation_gate_status: str  # "PASS" | "FAIL"
    overall_status: str  # "DEPLOYED" | "DRY_RUN_COMPLETE" | "ABORTED"
    steps: List[DeploymentStep] = field(default_factory=list)
    generated_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict:
        return {
            "repo_name": self.repo_name,
            "deployment_mode": self.deployment_mode,
            "validation_gate_status": self.validation_gate_status,
            "overall_status": self.overall_status,
            "generated_at": self.generated_at,
            "steps": [s.to_dict() for s in self.steps],
        }
