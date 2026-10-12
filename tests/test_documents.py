"""Zip aç / oluştur: Turkish names, no path escapes, nothing overwritten unless asked."""
import zipfile
from types import SimpleNamespace

import pytest

from rpa_orkestrai.actions.documents import zip_files
from rpa_orkestrai.errors import WorkflowError


def ctx():
    return SimpleNamespace(log=lambda message: None)


def test_create_then_extract_keeps_folders_and_turkish_names(tmp_path):
    source = tmp_path / "Raporlar"
    (source / "İade Şubat").mkdir(parents=True)
    (source / "İade Şubat" / "çağrı özeti.txt").write_text("içerik ğüşıöç", encoding="utf-8")
    single = tmp_path / "fatura.csv"
    single.write_text("no;tutar\n1;10", encoding="utf-8")
    archive = tmp_path / "çıktı" / "paket.zip"
    made = zip_files(ctx(), {"operation": "create", "items": f"{source}\n\n{single}", "destination": str(archive)})
    assert made["count"] == 2 and sorted(made["files"]) == ["Raporlar/İade Şubat/çağrı özeti.txt", "fatura.csv"]
    target = tmp_path / "açılan"
    opened = zip_files(ctx(), {"operation": "extract", "source": str(archive), "folder": str(target)})
    assert opened["count"] == 2
    assert (target / "Raporlar" / "İade Şubat" / "çağrı özeti.txt").read_text(encoding="utf-8") == "içerik ğüşıöç"
    # Nothing is replaced unless asked; with overwrite the same archive opens again.
    with pytest.raises(WorkflowError, match="aynı adlı"):
        zip_files(ctx(), {"operation": "extract", "source": str(archive), "folder": str(target)})
    assert zip_files(ctx(), {"operation": "extract", "source": str(archive), "folder": str(target),
                             "overwrite": True})["count"] == 2
    with pytest.raises(WorkflowError, match="aynı adlı"):
        zip_files(ctx(), {"operation": "create", "items": str(single), "destination": str(archive)})


def test_windows_explorer_names_in_cp857_are_decoded(tmp_path):
    archive = tmp_path / "windows.zip"
    # What Explorer stores: the name in OEM bytes (cp857) and no UTF-8 flag. zipfile would set
    # the flag for any non-ASCII name, so an ASCII name of the same length is replaced in the bytes.
    raw = "İŞLEM_ğüç.txt".encode("cp857")
    placeholder = b"Q" * (len(raw) - 4) + b".txt"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr(placeholder.decode("ascii"), b"veri")
    archive.write_bytes(archive.read_bytes().replace(placeholder, raw))
    with zipfile.ZipFile(archive) as check:
        assert not check.infolist()[0].flag_bits & 0x800
    zip_files(ctx(), {"operation": "extract", "source": str(archive), "folder": str(tmp_path / "out")})
    assert (tmp_path / "out" / "İŞLEM_ğüç.txt").read_bytes() == b"veri"


@pytest.mark.parametrize("name", ["../kacak.txt", "/mutlak.txt", "a/../../kacak.txt", "C:/kacak.txt", "..\\kacak.txt"])
def test_entries_leaving_the_folder_stop_before_any_file_is_written(tmp_path, name):
    archive = tmp_path / "kotu.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("once.txt", b"ok")
        handle.writestr(name, b"x")
    target = tmp_path / "hedef"
    with pytest.raises(WorkflowError, match="klasör dışına"):
        zip_files(ctx(), {"operation": "extract", "source": str(archive), "folder": str(target)})
    assert not (target / "once.txt").exists() and not (tmp_path / "kacak.txt").exists()


def test_invalid_requests_are_explained(tmp_path):
    (tmp_path / "bozuk.zip").write_bytes(b"not a zip")
    with pytest.raises(WorkflowError, match="bozuk"):
        zip_files(ctx(), {"operation": "extract", "source": str(tmp_path / "bozuk.zip"), "folder": str(tmp_path)})
    with pytest.raises(WorkflowError, match="bulunamadı"):
        zip_files(ctx(), {"operation": "extract", "source": str(tmp_path / "yok.zip"), "folder": str(tmp_path)})
    with pytest.raises(WorkflowError, match=".zip"):
        zip_files(ctx(), {"operation": "create", "items": str(tmp_path), "destination": str(tmp_path / "a.rar")})
    with pytest.raises(WorkflowError, match="bulunamadı"):
        zip_files(ctx(), {"operation": "create", "items": str(tmp_path / "yok"), "destination": str(tmp_path / "a.zip")})
    with pytest.raises(WorkflowError, match="arasında"):
        zip_files(ctx(), {"operation": "create", "items": str(tmp_path), "destination": str(tmp_path / "ic.zip")})


# ----- PDF'ten oku ---------------------------------------------------------------------------
import platform  # noqa: E402

from rpa_orkestrai.actions.documents import read_pdf  # noqa: E402


def write_pdf(target, pages):
    """A small valid PDF: each page is a content stream using Helvetica (/F1)."""
    objects = ["<< /Type /Catalog /Pages 2 0 R >>", None,
               "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"]
    kids = []
    for stream in pages:
        data = stream.encode("latin-1")
        objects.append(f"<< /Length {len(data)} >>\nstream\n{stream}\nendstream")
        objects.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 3 0 R >> >> "
                       f"/Contents {len(objects)} 0 R >>")
        kids.append(f"{len(objects)} 0 R")
    objects[1] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(kids)} >>"
    out, offsets = bytearray(b"%PDF-1.4\n"), []
    for number, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n{body}\nendobj\n".encode("latin-1")
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += "".join(f"{offset:010d} 00000 n \n" for offset in offsets).encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    target.write_bytes(bytes(out))


def text_at(x, y, value):
    return f"BT /F1 12 Tf {x} {y} Td ({value}) Tj ET"


def grid_page(rows):
    """A ruled table: every cell has drawn borders, as accounting PDFs do."""
    parts, top, height, widths = [], 700, 24, [120, 160, 100]
    for r, row in enumerate(rows):
        y, x = top - r * height, 60
        for c, value in enumerate(row):
            parts.append(f"{x} {y - height} {widths[c]} {height} re S")
            parts.append(text_at(x + 4, y - 17, value))
            x += widths[c]
    return "\n".join(parts)


def pdf_ctx():
    return SimpleNamespace(log=lambda message, **kw: None, check_cancelled=lambda: None,
                           config={"ocr_language": "tur+eng", "tesseract_cmd": ""},
                           settings=SimpleNamespace(action_timeout=30))


def test_pdf_text_from_chosen_pages(tmp_path):
    source = tmp_path / "fatura.pdf"
    write_pdf(source, [text_at(72, 720, "Fatura No: INV-1069"), text_at(72, 720, "Toplam: 1.250,50 TRY"),
                       text_at(72, 720, "Son sayfa")])
    every = read_pdf(pdf_ctx(), {"path": str(source)})
    assert "INV-1069" in every and "1.250,50" in every and "Son sayfa" in every
    assert read_pdf(pdf_ctx(), {"path": str(source), "pages": "2"}).strip() == "Toplam: 1.250,50 TRY"
    assert "INV-1069" not in read_pdf(pdf_ctx(), {"path": str(source), "pages": "2-3"})
    with pytest.raises(WorkflowError, match="3 sayfa"):
        read_pdf(pdf_ctx(), {"path": str(source), "pages": "4"})
    with pytest.raises(WorkflowError, match="biçiminde"):
        read_pdf(pdf_ctx(), {"path": str(source), "pages": "bir"})


def test_pdf_table_becomes_rows_named_by_headers(tmp_path):
    source = tmp_path / "liste.pdf"
    write_pdf(source, [text_at(72, 760, "Iade listesi") + "\n" + grid_page(
        [["Kod", "Aciklama", "Tutar"], ["A125", "Motor", "10,50"], ["A126", "Pompa", "7"]])])
    rows = read_pdf(pdf_ctx(), {"path": str(source), "mode": "table"})
    assert rows == [{"Kod": "A125", "Aciklama": "Motor", "Tutar": "10,50"},
                    {"Kod": "A126", "Aciklama": "Pompa", "Tutar": "7"}]
    plain = read_pdf(pdf_ctx(), {"path": str(source), "mode": "table", "header": False})
    assert plain[0] == {"sutun_1": "Kod", "sutun_2": "Aciklama", "sutun_3": "Tutar"} and len(plain) == 3
    with pytest.raises(WorkflowError, match="2. tablo yok"):
        read_pdf(pdf_ctx(), {"path": str(source), "mode": "table", "table": 2})


def test_unreadable_pdfs_are_explained(tmp_path):
    (tmp_path / "bozuk.pdf").write_bytes(b"%PDF-1.4 bozuk")
    with pytest.raises(WorkflowError, match="bozuk"):
        read_pdf(pdf_ctx(), {"path": str(tmp_path / "bozuk.pdf")})
    with pytest.raises(WorkflowError, match="bulunamadı"):
        read_pdf(pdf_ctx(), {"path": str(tmp_path / "yok.pdf")})
    with pytest.raises(WorkflowError, match=".pdf"):
        read_pdf(pdf_ctx(), {"path": str(tmp_path / "belge.docx")})


@pytest.mark.skipif(platform.system() not in {"Darwin", "Windows"}, reason="system OCR")
def test_scanned_pdf_page_is_read_with_system_ocr(tmp_path):
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGB", (1200, 400), "white")
    try:
        font = ImageFont.load_default(size=72)
    except TypeError:
        font = ImageFont.load_default()
    ImageDraw.Draw(image).text((60, 140), "INVOICE 2026", fill="black", font=font)
    source = tmp_path / "taranmis.pdf"
    image.save(source, "PDF", resolution=150)
    assert "INVOICE" in read_pdf(pdf_ctx(), {"path": str(source)}).upper()
    assert read_pdf(pdf_ctx(), {"path": str(source), "ocr": False}) == ""
