"""Scenario recall plugin, with the same deterministic local grading as cloze."""

from app.domain.exercises import (
    AnswerSpec,
    ExerciseContext,
    ExercisePrompt,
    GeneratedExercise,
    Unavailable,
)
from app.services.exercise_answers import grade_answer, selected_lexeme_forms
from app.services.exercise_registry import ExercisePlugin, ExerciseRegistry, ScenarioProvider
from app.services.scenario import ScenarioText, valid_scenario


def register(target: ExerciseRegistry, provider: ScenarioProvider) -> None:
    async def generate(context: ExerciseContext) -> GeneratedExercise | Unavailable:
        forms = selected_lexeme_forms(context.lemma, context.lexeme)
        if not forms:
            return Unavailable(exercise="scenario", reason="missing_forms")
        context = context.model_copy(update={"forms": forms})
        source = await provider(context)
        if isinstance(source, Unavailable):
            return source
        try:
            valid = valid_scenario(ScenarioText(scenario=source.scenario), forms)
        except ValueError:
            valid = False
        if not valid:
            return Unavailable(exercise="scenario", reason="rejected_response")
        return GeneratedExercise(
            prompt=ExercisePrompt(text=source.scenario, input="text"),
            private=AnswerSpec(answer=str(context.lemma.fields["text"]), accepted_forms=forms),
        )

    target.register(ExercisePlugin("scenario", "recall", generate, grade_answer))
