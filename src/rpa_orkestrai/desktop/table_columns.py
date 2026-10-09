"""Clipboard column names shared by desktop table reading and writing."""
import re


def clipboard_rows(value):
    """Ignore separator lines, but preserve tab-delimited empty records/columns."""
    lines = str(value).replace("\r\n", "\n").replace("\r", "\n").split("\n")
    return tuple(tuple(cell.strip() for cell in line.split("\t"))
                 for line in lines if line.strip() or "\t" in line)


def split_header(cells, *, header, header_row=1):
    """Only a chosen header may exclude preceding rows; never guess by content."""
    if type(header_row) is not int or not 1 <= header_row <= 10_000:
        raise ValueError("Başlık satırı 1–10.000 arasında bir tam sayı olmalıdır.")
    if not header:
        return (), cells, ()
    if not cells or header_row > len(cells):
        raise ValueError("Seçilen başlık satırı kopyalanan tabloda yok; tabloyu yeniden seçin.")
    return cells[header_row - 1], cells[header_row:], cells[:header_row - 1]


def folded(value):
    return str(value).replace("İ", "i").replace("I", "i").replace("ı", "i").casefold()


def column_names(titles, width):
    names = []
    for index in range(width):
        name = titles[index] if index < len(titles) and titles[index] else f"sutun_{index + 1}"
        base, counter = name, 2
        while name in names:
            name, counter = f"{base} ({counter})", counter + 1
        names.append(name)
    return names


def numbered_column(value):
    """One-based number/alias; actual copied names take precedence at the caller."""
    match = re.fullmatch(r"(?:s[uü]tun_)?([1-9][0-9]{0,3})", folded(value).strip())
    return int(match[1]) - 1 if match else None


def resolve_column(names, value):
    wanted = folded(value).strip()
    matches = [i for i, name in enumerate(names) if folded(name) == wanted]
    if len(matches) == 1:
        return matches[0]
    if matches:
        raise ValueError("Birden fazla sütun bu başlığa sahip; sütun numarasını kullanın.")
    index = numbered_column(value)
    if index is not None and index < len(names):
        return index
    raise ValueError(f"Tabloda “{value}” sütunu yok. Okunan sütunlar: " + ", ".join(names)
                     + ". Sütun adı, sutun_2 gibi bir ad veya 1'den başlayan numara kullanın.")
