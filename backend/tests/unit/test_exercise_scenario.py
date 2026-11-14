import pytest
from fsrs import State
from pydantic import ValidationError

from app.domain.exercises import ExerciseContext, ScenarioSource, Unavailable
from app.services.exercise_scenario import register
from app.services.scenario import ScenarioText, valid_scenario
from tests.exercise_support import FakeGenerator, plugins
from tests.unit.test_exercise_framework import context, memory

TEXT = "The bus is leaving, so Maya moves quickly on foot to reach the stop."


@pytest.mark.parametrize(
    "text",
    [
        "You RUN to catch the last bus.",
        "She has ＲＡＮ across the road to catch her bus.",
        "A running child wants to catch the bus.",
        "She chooses to r-u-n across the road.",
        "She chooses to r u n across the road.",
        "The answer is a way of moving quickly.",
        "The spelling describes moving quickly on foot.",
        "It starts with r and describes moving quickly.",
        "Move ____ to catch the departing bus.",
        "Move <b>quickly</b> to catch the departing bus.",
        "She moves quickly.\nThe bus is leaving.",
        "She moves quickly.\u2028The bus is leaving.",
        "**Someone moves quickly** to catch a departing bus.",
        "A) move quickly B) stay in the same place.",
        "The bus is leav\u200bing; she moves quickly.",
        " One person moves quickly to catch the bus.",
        "A sentence. A second. A third. A fourth.",
    ],
)
def test_rejects_answer_leaks_and_malformed_scenarios(text: str) -> None:
    assert not valid_scenario(ScenarioText(scenario=text), ("run", "ran", "running"))


@pytest.mark.parametrize(
    "data", [{}, {"scenario": "short"}, {"scenario": 42}, {"scenario": TEXT, "answer": "run"}]
)
def test_strict_schema(data: dict) -> None:
    with pytest.raises(ValidationError):
        ScenarioText.model_validate(data, strict=True)


def test_valid_scenario_and_phrase_leaks() -> None:
    assert valid_scenario(ScenarioText(scenario=TEXT), ("run", "ran", "running"))
    assert not valid_scenario(
        ScenarioText(scenario="She decides to give-up before the difficult exam."), ("give up",)
    )


async def test_plugin_grades_selected_forms_locally_without_exposing_them() -> None:
    calls = 0

    async def provider(context: ExerciseContext) -> ScenarioSource:
        nonlocal calls
        calls += 1
        return ScenarioSource(scenario=TEXT, represented_form="run")

    target = plugins()
    register(target, provider)
    plugin = target.get("scenario")
    generated = await plugin.generate(context())
    assert not isinstance(generated, Unavailable)
    assert generated.prompt.input == "text"
    assert generated.prompt.text == TEXT
    assert "accepted_forms" not in generated.prompt.model_dump()
    assert plugin.grade(generated.private, " ＲＡＮ ").correct
    assert plugin.grade(generated.private, "running").correct
    assert not plugin.grade(generated.private, "runner").correct
    assert calls == 1


@pytest.mark.parametrize(
    "reason", ["disabled", "budget_exhausted", "timeout", "generation_pending", "provider_error"]
)
async def test_unavailable_scenario_selects_another_type_with_reason(reason: str) -> None:
    async def provider(context: ExerciseContext) -> Unavailable:
        return Unavailable(exercise="scenario", reason=reason)

    target = plugins(FakeGenerator("offline", "recognition"))
    register(target, provider)
    selected = await target.select(context(), memory(State.Review), random_value=lambda: 0)
    assert selected.plugin.exercise == "offline"
    assert selected.skipped == (Unavailable(exercise="scenario", reason=reason),)


async def test_plugin_rechecks_provider_output_and_state() -> None:
    async def unsafe(context: ExerciseContext) -> ScenarioSource:
        return ScenarioSource(scenario="She is running to catch the bus.", represented_form="run")

    target = plugins(FakeGenerator("offline", "recognition"))
    register(target, unsafe)
    assert isinstance(await target.get("scenario").generate(context()), Unavailable)
    selected = await target.select(context(), memory(State.Learning))
    assert selected.skipped[0].reason == "card_state"
