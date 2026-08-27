import pytest

from pylens.ocr.preprocess import choose_scale


@pytest.mark.parametrize(
    ("profile", "expected_longest"),
    [
        ("fast", 1920),
        ("balanced", 2560),
        ("accuracy", 3200),
    ],
)
def test_profile_scale_targets_bounded_longest_side(profile: str, expected_longest: int):
    scale = choose_scale(1200, 900, profile)
    assert round(1200 * scale) == expected_longest


def test_large_capture_is_downscaled_instead_of_exceeding_cpu_bound():
    scale = choose_scale(7680, 4320, "balanced")
    assert round(7680 * scale) == 2560


def test_tiny_capture_is_not_enlarged_more_than_three_times():
    assert choose_scale(100, 50, "balanced") == 3.0


def test_unknown_profile_is_rejected():
    with pytest.raises(ValueError, match="Unknown OCR profile"):
        choose_scale(800, 600, "maximum")
