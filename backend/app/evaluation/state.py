"""
Shared constants and per-evaluation decision-memory paths.

There is no process-global interview session anymore. Every evaluation is
identified by its database row ID (`evaluation_id`), and the database is the
single source of truth for status, current round, and round history. This
avoids the class of bugs where a shared in-memory dict is read/written by
concurrent requests for different candidates.
"""

import os

VERDICTS_DIR = os.path.join(os.path.dirname(__file__), "verdicts")


# Available interview roles
AVAILABLE_ROLES = [
    "SDE 1",
    "SDE 2",
    "Senior Software Engineer",
    "AI Engineer",
    "ML Engineer",
    "Backend Developer",
    "Frontend Developer",
    "Full-Stack Developer",
    "DevOps Engineer",
    "Data Scientist",
]


# Pipeline stage definitions
PIPELINE_STAGES = [
    {"stage": 1, "name": "Resume Screening", "agent": "Screening Agent", "requires_input": False},
    {"stage": 2, "name": "Technical Interview", "agent": "Technical Agent", "requires_input": True},
    {"stage": 3, "name": "Behavioral Interview", "agent": "Behavioral Agent", "requires_input": True},
    {"stage": 4, "name": "Hiring Recommendation", "agent": "Recommendation Agent", "requires_input": False},
    {"stage": 5, "name": "Committee Decision", "agent": "Committee Evaluator", "requires_input": False},
]


def eval_verdicts_dir(evaluation_id: int) -> str:
    """Return the decision-memory directory for one evaluation.

    Each evaluation gets its own subdirectory keyed by ID, so concurrent
    evaluations can never read or overwrite each other's verdict files.
    """
    path = os.path.join(VERDICTS_DIR, str(evaluation_id))
    os.makedirs(path, exist_ok=True)
    return path


# Ensure verdicts directory exists on import
os.makedirs(VERDICTS_DIR, exist_ok=True)
