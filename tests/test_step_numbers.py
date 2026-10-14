"""Her adım türünün kütüphane numarası sabittir; akıştaki sıradan etkilenmez."""

from rpa_orkestrai.catalog import CATALOG
from rpa_orkestrai.engine import step_numbers
from rpa_orkestrai.models import Step
from rpa_orkestrai.step_numbers import STEP_NUMBERS

# Yayımlanmış numaralar: değişirse akış belgeleri ve kılavuz yanlış adımı gösterir.
PINNED = {"desktop.find_window": 1, "desktop.window_click": 2, "desktop.window_fill": 3, "desktop.window_key": 4}


def test_every_library_step_has_one_unique_number_and_published_numbers_never_move():
    assert {entry["type"] for entry in CATALOG} <= set(STEP_NUMBERS)
    assert len(set(STEP_NUMBERS.values())) == len(STEP_NUMBERS)
    assert sorted(STEP_NUMBERS.values()) == list(range(1, len(STEP_NUMBERS) + 1))
    for kind, number in PINNED.items():
        assert STEP_NUMBERS[kind] == number
    assert all(entry["number"] == STEP_NUMBERS[entry["type"]] for entry in CATALOG)


def test_flow_numbers_follow_the_step_type_not_the_position():
    steps = [Step(id="a", action="desktop.window_fill"), Step(id="b", action="desktop.find_window"),
             Step(id="c", action="control.if", children=[Step(id="d", action="desktop.window_fill")])]
    numbers = step_numbers(steps)
    assert numbers["a"] == numbers["d"] == str(STEP_NUMBERS["desktop.window_fill"])
    assert numbers["b"] == "1" and numbers["c"] == str(STEP_NUMBERS["control.if"])
    steps.reverse()
    assert step_numbers(steps) == numbers
