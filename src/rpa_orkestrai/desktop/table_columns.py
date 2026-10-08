"""Clipboard column names shared by desktop table reading and writing."""
import re


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
