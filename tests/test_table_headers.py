"""Headers are selected from the export, never inferred from business vocabulary."""
import pytest

from rpa_orkestrai.actions.windows import table_of
from rpa_orkestrai.desktop.screen_tables import TableText
from rpa_orkestrai.desktop.windows import WindowError


@pytest.mark.parametrize("prefix", [False, True])
def test_exported_headings_are_not_record_one_after_selection(prefix):
    headings = [""] * 36
    headings[6:9] = ["Fatura No", "Hasarlı", "İade Sonrası"]
    record = [""] * 36
    record[6:9] = ["02103500", "", "ARIZALILAR"]
    raw = (["\t" * 35] if prefix else []) + ["\t".join(headings), "\t".join(record)]
    text = "\r\n".join(raw)
    before = TableText.parse(text, header=prefix)
    assert before.names[6] == "sutun_7" and len(before.rows) == 2
    assert before.rows[0][6] == "Fatura No"
    preview = before.preview()
    choice = next(v for v in preview["variants"] if v["header"] and v["header_row"] == 1 + prefix)
    assert choice["rows"] == 1 and choice["columns"][6] == "Fatura No"
    assert choice["sample_rows"][0][6] == "02103500"
    after = TableText.parse(text, header=True, header_row=1 + prefix)
    names, rows = table_of(text, header=True, header_row=1 + prefix)
    assert names == after.names and rows == [list(r) for r in after.rows]
    assert after.select(row_mode="index", row=1, column="sutun_9", match_column="", match_value="") == (0, 8)
    assert after.column("İade Sonrası") == after.column("sutun_9") == 8


def test_real_empty_record_and_business_words_are_never_removed_implicitly():
    text = "Kod\tDurum\n\t\nFatura No\tİade Sonrası\nA125\tREADY"
    for header in (True, False):
        table = TableText.parse(text, header=header)
        names, rows = table_of(text, header=header)
        assert names == table.names and rows == [list(r) for r in table.rows]
        assert len(rows) == (3 if header else 4)
        assert ["", ""] in rows and ["Fatura No", "İade Sonrası"] in rows


def test_single_export_row_can_be_previewed_and_demoted_from_header():
    preview = TableText.parse("A125\tREADY", allow_empty=True).preview()
    assert preview["rows"] == 0
    headerless = preview["variants"][0]
    assert headerless["rows"] == 1 and headerless["sample_rows"] == [["A125", "READY"]]
    with pytest.raises(WindowError, match="veri satırı"):
        TableText.parse("A125\tREADY")


@pytest.mark.parametrize("position", [0, -1, 1.5, True, 10001, 3])
def test_invalid_or_missing_heading_cannot_select_a_record(position):
    with pytest.raises(WindowError, match="Başlık|başlık"):
        TableText.parse("Kod\tDurum\nA125\tREADY", header_row=position)
