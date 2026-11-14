import pytest

from app.services.exercise_image import safe_attribution


@pytest.mark.parametrize(
    "attribution",
    [
        "Photo by Runner",
        "https://pixabay.com/photos/running-123/",
        "https://example.com/%72%75%6e",
        "Photo by ＲＵＮ",
        "r&#117;n",
        "https://example.com/%2572%2575%256e",
    ],
)
def test_attribution_never_reveals_any_selected_form(attribution: str) -> None:
    assert not safe_attribution(attribution, ("run", "ran", "running"))


@pytest.mark.parametrize("attribution", [None, "Photo by Alice · https://pixabay.com/photos/123/"])
def test_safe_attribution_is_retained_verbatim(attribution: str | None) -> None:
    assert safe_attribution(attribution, ("run", "ran", "running"))
