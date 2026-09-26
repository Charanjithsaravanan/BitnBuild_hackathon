from __future__ import annotations

import hashlib
import json
import random
import secrets
from typing import Any


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def definition_hash(definition: dict) -> str:
    return hashlib.sha256(canonical_json(definition).encode("utf-8")).hexdigest()


def generate_seed() -> str:
    return secrets.token_hex(16)


def choose_condition_group(groups: list[str], seed: str) -> str | None:
    if not groups:
        return None
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    index = int.from_bytes(digest[:8], "big") % len(groups)
    return groups[index]


def compile_execution_plan(definition: dict, seed: str) -> list[dict]:
    """Expand trial groups into a reproducible per-session plan.

    Non-trial blocks remain as explicit steps. Branches are dynamic and are
    therefore kept as block steps; the browser runner decides their target.
    """
    rng = random.Random(seed)
    settings = definition.get("settings", {})
    global_randomize = bool(settings.get("randomize_trials", False))
    steps: list[dict] = []
    trial_steps: list[dict] = []

    for block in definition.get("blocks", []):
        if block.get("type") == "consent":
            # Consent is collected before a session is created; do not repeat it in the flow.
            continue
        if block.get("type") != "trial_group":
            steps.append({"kind": "block", "block_id": block["id"]})
            continue

        data = block.get("data") or {}
        trials = data.get("trials") or []
        repetitions = max(1, min(int(data.get("repetitions", 1)), 1000))
        group_randomize = bool(data.get("randomize", False)) or global_randomize

        group_items = []
        for repetition in range(repetitions):
            for trial in trials:
                trial = dict(trial)
                item = {
                    "kind": "trial",
                    "group_id": block["id"],
                    "trial_id": str(trial.get("id")),
                    "trial_index": 0,
                    "repetition": repetition,
                    "trial": trial,
                }
                group_items.append(item)

        if group_randomize:
            rng.shuffle(group_items)
        trial_steps.extend(group_items)
        # Marker makes it possible to jump to a group via a branch.
        steps.append({"kind": "group_marker", "group_id": block["id"]})

    if global_randomize and len(trial_steps) > 1:
        rng.shuffle(trial_steps)
        first_marker = next((i for i, step in enumerate(steps) if step["kind"] == "group_marker"), None)
        if first_marker is None:
            final_steps = steps[:]
            final_steps.extend(trial_steps)
        else:
            cleaned = [step for step in steps if step["kind"] != "group_marker"]
            final_steps = cleaned[:first_marker] + trial_steps + cleaned[first_marker:]
    else:
        trial_by_group: dict[str, list[dict]] = {}
        for item in trial_steps:
            trial_by_group.setdefault(item["group_id"], []).append(item)
        final_steps = []
        for step in steps:
            if step["kind"] == "group_marker":
                final_steps.extend(trial_by_group.get(step["group_id"], []))
            else:
                final_steps.append(step)

    for idx, step in enumerate(final_steps):
        step["execution_index"] = idx
    return final_steps


def build_step_lookup(plan: list[dict]) -> dict[str, int]:
    lookup: dict[str, int] = {}
    for idx, step in enumerate(plan):
        if step.get("kind") == "block":
            lookup[step["block_id"]] = idx
        elif step.get("kind") == "trial":
            lookup[f"{step['group_id']}::{step['trial_id']}::{step['repetition']}"] = idx
            lookup.setdefault(step["group_id"], idx)
    return lookup
