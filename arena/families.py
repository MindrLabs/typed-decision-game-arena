"""Request and response shapes of model-compose's `typed-decision` task, per model family.

Every family receives byte-identical sentences: the state as `text`, the instructions, and one description per
option. Only the JSON around them differs, because the families declare questions differently:

* clef, kev, laya: `{qid: {type: "choice", instructions, criteria: {key: description}}}`
* nimble:          `{qid: {type: "enum", choices: [key...], description, choice_descriptions: {key: description}}}`

All four drivers answer `{decision: {qid: key}, fields: {qid: {scores: {key: probability}}}}`.
Options keep the order given (Python dicts and JSON objects preserve insertion order end to end).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from arena.core import JSON, Question

QUESTION_ID = "move"
CHOICE_FAMILIES = frozenset({"clef", "kev", "laya"})
ENUM_FAMILIES = frozenset({"nimble"})
FAMILIES = CHOICE_FAMILIES | ENUM_FAMILIES


class ResponseError(ValueError):
    """The model server answered, but not with a usable decision."""


def payload(family: str, question: Question) -> JSON:
    descriptions = {option.key: option.text for option in question.options}
    if family in CHOICE_FAMILIES:
        schema: JSON = {
            QUESTION_ID: {"type": "choice", "instructions": question.instructions, "criteria": descriptions}
        }
    elif family in ENUM_FAMILIES:
        schema = {
            QUESTION_ID: {
                "type": "enum",
                "choices": list(descriptions),
                "description": question.instructions,
                "choice_descriptions": descriptions,
            }
        }
    else:
        raise ValueError(f"unknown typed-decision family {family!r}; known: {sorted(FAMILIES)}")
    return {"text": question.state, "schema": schema}


def parse(output: Any, shown: Sequence[str]) -> tuple[str, dict[str, float] | None]:
    """The chosen key and the per-option probabilities (when returned) from a workflow output."""
    if not isinstance(output, Mapping):
        raise ResponseError(f"expected an object, got {type(output).__name__}")
    decision = output.get("decision")
    if not isinstance(decision, Mapping) or QUESTION_ID not in decision:
        raise ResponseError(f"no decision for {QUESTION_ID!r} in {output!r:.300}")
    choice = decision[QUESTION_ID]
    if not isinstance(choice, str) or choice not in shown:
        raise ResponseError(f"decision {choice!r} is not one of the options shown {list(shown)}")
    scores = None
    fields = output.get("fields")
    if isinstance(fields, Mapping):
        field = fields.get(QUESTION_ID)
        if isinstance(field, Mapping) and isinstance(field.get("scores"), Mapping):
            scores = {str(k): float(v) for k, v in field["scores"].items()}
    return choice, scores
