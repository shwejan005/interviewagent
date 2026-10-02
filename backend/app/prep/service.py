"""LLM-assisted preparation planning with a deterministic fallback.

The LLM is used only when a learner explicitly generates a roadmap or problem.
Catalog reads and code execution never wait on a model provider.
"""

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


def _extract_json(raw: str) -> dict[str, Any]:
    candidate = raw.strip()
    if "```" in candidate:
        candidate = re.sub(r"```(?:json)?", "", candidate, flags=re.IGNORECASE).replace("```", "").strip()
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("The planner did not return a JSON object.")
    value = json.loads(candidate[start : end + 1])
    if not isinstance(value, dict):
        raise ValueError("The planner returned an invalid JSON object.")
    return value


def _fallback_plan(goal: dict, problems: list[dict]) -> dict[str, Any]:
    level = goal.get("current_level", "BEGINNER")
    focus = set(goal.get("focus_topics") or [])
    difficulty_order = {"EASY": 0, "MEDIUM": 1, "HARD": 2, "APPLIED": 3}
    target_level = {"BEGINNER": 0, "INTERMEDIATE": 1, "ADVANCED": 2}.get(level, 0)
    ranked = sorted(
        problems,
        key=lambda problem: (
            0 if problem.get("topic_slug") in focus else 1,
            abs(difficulty_order.get(problem.get("difficulty"), 0) - target_level),
            problem.get("id", 0),
        ),
    )
    selected = [problem["slug"] for problem in ranked[: max(3, min(8, len(ranked)))] if problem.get("slug")]
    return {
        "title": f"{goal.get('target_role', 'Software Engineer')} interview plan",
        "summary": f"A {level.lower()}-level DSA plan built around {goal.get('daily_minutes', 45)} minutes a day, {goal.get('days_per_week', 5)} days a week.",
        "weekly_focus": ["Learn the pattern", "Solve a timed problem", "Review and explain the trade-offs"],
        "problem_slugs": selected,
        "daily_schedule": [
            {"day": "Mon", "activity": "Concept lesson + one easy problem", "minutes": goal.get("daily_minutes", 45)},
            {"day": "Tue", "activity": "Guided problem attempt", "minutes": goal.get("daily_minutes", 45)},
            {"day": "Wed", "activity": "Timed problem", "minutes": goal.get("daily_minutes", 45)},
            {"day": "Thu", "activity": "Review mistakes and retry", "minutes": goal.get("daily_minutes", 45)},
            {"day": "Fri", "activity": "Interview explanation practice", "minutes": goal.get("daily_minutes", 45)},
        ],
        "generated_by": "heuristic",
    }


def generate_roadmap_plan(goal: dict, topics: list[dict], problems: list[dict]) -> dict[str, Any]:
    """Ask the configured CrewAI provider for a structured plan, then validate it."""
    fallback = _fallback_plan(goal, problems)
    try:
        from crewai import Agent, Crew, Task
        from app.evaluation.agents import LLM_MODEL

        context = {
            "goal": goal,
            "topics": [{"slug": topic["slug"], "name": topic["name"], "difficulty": topic["difficulty"]} for topic in topics],
            "problems": [
                {"slug": problem["slug"], "title": problem["title"], "topic_slug": problem["topic_slug"], "difficulty": problem["difficulty"], "minutes": problem["estimated_minutes"]}
                for problem in problems
            ],
        }
        agent = Agent(
            role="Personalized DSA Learning Architect",
            goal="Design a realistic, motivating interview preparation plan from a learner's constraints.",
            backstory="You sequence DSA patterns progressively and respect the learner's available time. You never invent problem slugs.",
            llm=LLM_MODEL,
            verbose=False,
            allow_delegation=False,
        )
        task = Task(
            description=(
                "Create a personalized DSA roadmap from this JSON context:\n"
                f"{json.dumps(context, separators=(',', ':'))}\n\n"
                "Return ONLY JSON with keys: title, summary, weekly_focus (array of strings), "
                "problem_slugs (array using only known slugs), daily_schedule (array of objects with day, activity, minutes). "
                "Respect daily_minutes and days_per_week. Prefer a progression from foundational to target-level problems."
            ),
            expected_output="A single valid JSON object with the requested keys.",
            agent=agent,
        )
        raw = str(Crew(agents=[agent], tasks=[task], verbose=False).kickoff())
        plan = _extract_json(raw)
        known = {problem["slug"] for problem in problems}
        selected = [slug for slug in plan.get("problem_slugs", []) if slug in known]
        if not selected:
            return fallback
        plan["problem_slugs"] = selected[:12]
        plan["generated_by"] = "llm"
        plan.setdefault("weekly_focus", fallback["weekly_focus"])
        plan.setdefault("daily_schedule", fallback["daily_schedule"])
        return plan
    except Exception as exc:
        logger.warning("Prep roadmap LLM unavailable; using deterministic plan: %s", exc)
        return fallback


def generate_problem(topic: dict, difficulty: str, language: str) -> dict[str, Any]:
    """Generate one executable problem contract for an explicit learner request."""
    try:
        from crewai import Agent, Crew, Task
        from app.evaluation.agents import LLM_MODEL

        agent = Agent(
            role="DSA Problem Author",
            goal="Write a precise, interview-quality coding problem with executable examples.",
            backstory="You write self-contained problems, realistic constraints, and deterministic test cases. You never use system design topics in this DSA workspace.",
            llm=LLM_MODEL,
            verbose=False,
            allow_delegation=False,
        )
        task = Task(
            description=(
                f"Create a {difficulty} DSA problem for the topic {topic['name']} ({topic['slug']}) using {language}. "
                "Return ONLY JSON with keys: title, prompt, difficulty, estimated_minutes, expected_concepts, constraints, hint, "
                "starter_code (object keyed by language), harnesses (object keyed by language; use {{INPUT}} placeholder), "
                "test_cases (array of title, input object, expected_output string, explanation, is_hidden). "
                "Provide at least two visible cases and one hidden case. The harness must invoke the submitted solution and print JSON."
            ),
            expected_output="A single valid JSON problem contract.",
            agent=agent,
        )
        problem = _extract_json(str(Crew(agents=[agent], tasks=[task], verbose=False).kickoff()))
        required = ("title", "prompt", "constraints", "hint", "starter_code", "harnesses", "test_cases")
        if any(not problem.get(key) for key in required) or not problem.get("test_cases"):
            raise ValueError("The generated problem was incomplete.")
        problem["topic_slug"] = topic["slug"]
        problem["difficulty"] = difficulty
        problem["estimated_minutes"] = int(problem.get("estimated_minutes", 35))
        return problem
    except Exception as exc:
        logger.warning("Prep problem generation failed: %s", exc)
        raise ValueError("The problem generator is unavailable. Check the configured LLM provider and try again.") from exc
