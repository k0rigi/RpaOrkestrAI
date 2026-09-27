from unittest.mock import Mock

import pytest

from rpa_orkestrai.integrations import SheetsService


def make_service(values):
    service = SheetsService("unused.json", "sheet-id")
    service._worksheet = Mock()
    service._worksheet.get.return_value = values
    return service


def test_table_preserves_blank_status_and_formatted_ids_in_one_snapshot():
    service = make_service([
        ["00125", ""], ["00126", "Bekliyor"], ["00127"], ["00128", None],
        ["00129", "Tamamlandı"],
    ])

    assert service.get_rows() == [
        {"row_number": 2, "form_id": "00125", "status": ""},
        {"row_number": 3, "form_id": "00126", "status": "Bekliyor"},
        {"row_number": 4, "form_id": "00127", "status": ""},
        {"row_number": 5, "form_id": "00128", "status": ""},
        {"row_number": 6, "form_id": "00129", "status": "Tamamlandı"},
    ]
    service._worksheet.get.assert_called_once_with("B2:C101", value_render_option="FORMATTED_VALUE")


@pytest.mark.parametrize("blank", [[], [""], [None], [" \t ", "Bekliyor"]])
def test_table_stop_uses_only_key_field(blank):
    service = make_service([["00125", ""], blank, ["00127", "Bekliyor"]])
    assert service.get_rows(max_rows=3) == [{"row_number": 2, "form_id": "00125", "status": ""}]
    service._worksheet.get.assert_called_once_with("B2:C4", value_render_option="FORMATTED_VALUE")


def test_table_skip_preserves_physical_row_numbers_and_numeric_zero_key():
    service = make_service([
        [], ["00125", ""], ["", "Bekliyor"], [None, ""], [" \t ", ""],
        [0, 0], ["00126", " Bekliyor "],
    ])
    assert service.get_rows(start_row=5, max_rows=7, empty_policy="skip") == [
        {"row_number": 6, "form_id": "00125", "status": ""},
        {"row_number": 10, "form_id": "0", "status": "0"},
        {"row_number": 11, "form_id": "00126", "status": " Bekliyor "},
    ]
    service._worksheet.get.assert_called_once_with("B5:C11", value_render_option="FORMATTED_VALUE")


def test_table_orders_columns_numerically_and_honors_custom_key():
    service = make_service([
        ["Bekliyor", "ignored", "00125"], ["", "ignored", "00126"],
        ["completed", "ignored", ""],
    ])
    assert service.get_rows(
        start_row=12, max_rows=3, columns={"invoice": "$aa", "state": "Y"}, key="invoice",
    ) == [
        {"row_number": 12, "invoice": "00125", "state": "Bekliyor"},
        {"row_number": 13, "invoice": "00126", "state": ""},
    ]
    service._worksheet.get.assert_called_once_with("Y12:AA14", value_render_option="FORMATTED_VALUE")


def test_table_single_column_and_highest_a1_column_are_supported():
    service = make_service([["0001"]])
    assert service.get_rows(
        start_row=999_999, max_rows=2, columns={"id": "ZZZ"}, key="id",
    ) == [{"row_number": 999_999, "id": "0001"}]
    service._worksheet.get.assert_called_once_with(
        "ZZZ999999:ZZZ1000000", value_render_option="FORMATTED_VALUE",
    )


@pytest.mark.parametrize("policy", ["stop", "skip"])
def test_table_empty_sheet_returns_no_records(policy):
    service = make_service([])
    assert service.get_rows(empty_policy=policy) == []


@pytest.mark.parametrize("max_rows", [1, 1000])
def test_table_never_exceeds_requested_physical_rows(max_rows):
    service = make_service([[str(index), ""] for index in range(max_rows + 1)])
    rows = service.get_rows(max_rows=max_rows)
    assert len(rows) == max_rows
    assert rows[-1]["row_number"] == max_rows + 1
    service._worksheet.get.assert_called_once_with(
        f"B2:C{max_rows + 1}", value_render_option="FORMATTED_VALUE",
    )


@pytest.mark.parametrize("kwargs", [
    {"start_row": 0}, {"start_row": -1}, {"start_row": True}, {"start_row": "2"},
    {"start_row": 2.0}, {"start_row": 1_000_001}, {"start_row": 1_000_000, "max_rows": 2},
    {"max_rows": 0}, {"max_rows": -1}, {"max_rows": True}, {"max_rows": "2"},
    {"max_rows": 2.0}, {"max_rows": 1001}, {"empty_policy": "keep"}, {"empty_policy": None},
    {"columns": {}}, {"columns": "B:C"}, {"columns": [["form_id", "B"]]},
    {"columns": {"form_id": "B", "status": "b"}},
    {"columns": {"form_id": "$B", "status": "b"}},
    {"columns": {"form_id": "B", "row_number": "C"}},
    {"columns": {"form_id": "B", "__proto__": "C"}},
    {"columns": {"form_id": "B", "prototype": "C"}},
    {"columns": {"form_id": "B", "constructor": "C"}},
    {"columns": {"form_id": "B", "row.value": "C"}},
    {"columns": {"form_id": "B", "1state": "C"}},
    {"columns": {"form_id": "B", "": "C"}},
    {"columns": {"form_id": "B", "x" * 65: "C"}},
    {"columns": {"form_id": "B", 1: "C"}},
    {"columns": {"form_id": "B2"}}, {"columns": {"form_id": " B"}},
    {"columns": {"form_id": "B:C"}}, {"columns": {"form_id": "Sheet1!B"}},
    {"columns": {"form_id": "AAAA"}}, {"columns": {"form_id": ""}},
    {"columns": {"form_id": None}}, {"columns": {"form_id": 2}},
    {"columns": {"id": "B"}}, {"key": "missing"}, {"key": None}, {"key": ["form_id"]},
    {"columns": {"form_id": "A", "status": "BM"}},
    {"columns": {f"field_{i}": "B" for i in range(33)}, "key": "field_0"},
])
def test_table_validates_entire_request_before_opening_connection(kwargs):
    service = SheetsService("unused.json", "sheet-id")
    service._connect = Mock(side_effect=AssertionError("invalid input must not connect"))
    with pytest.raises(ValueError):
        service.get_rows(**kwargs)
    service._connect.assert_not_called()


def test_table_accepts_largest_column_span_without_returning_unmapped_values():
    service = make_service([["00125", *(["ignored"] * 62), ""]])
    assert service.get_rows(columns={"form_id": "A", "status": "BL"}, max_rows=1) == [
        {"row_number": 2, "form_id": "00125", "status": ""},
    ]
    service._worksheet.get.assert_called_once_with("A2:BL2", value_render_option="FORMATTED_VALUE")
