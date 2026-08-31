from __future__ import annotations

from pathlib import Path
from xml.sax.saxutils import escape
import zipfile


def _cell(reference: str, value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        return f'<c r="{reference}"><v>{value}</v></c>'
    text = escape(str(value))
    return f'<c r="{reference}" t="inlineStr"><is><t>{text}</t></is></c>'


def _column_name(index: int) -> str:
    value = index + 1
    result = ""
    while value:
        value, remainder = divmod(value - 1, 26)
        result = chr(ord("A") + remainder) + result
    return result


def write_xlsx(path: Path, sheets: dict[str, list[list[object | None]]]) -> Path:
    workbook_sheets = []
    relationships = []
    sheet_payloads: list[tuple[str, str]] = []
    for index, (name, rows) in enumerate(sheets.items(), start=1):
        workbook_sheets.append(f'<sheet name="{escape(name)}" sheetId="{index}" r:id="rId{index}"/>')
        relationships.append(
            f'<Relationship Id="rId{index}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{index}.xml"/>'
        )
        xml_rows = []
        for row_number, row in enumerate(rows, start=1):
            cells = "".join(
                _cell(f"{_column_name(column)}{row_number}", value)
                for column, value in enumerate(row)
                if value is not None
            )
            xml_rows.append(f'<row r="{row_number}">{cells}</row>')
        sheet_payloads.append((
            f"xl/worksheets/sheet{index}.xml",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            f'<sheetData>{"".join(xml_rows)}</sheetData></worksheet>',
        ))

    workbook = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'<sheets>{"".join(workbook_sheets)}</sheets></workbook>'
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        f'{"".join(relationships)}</Relationships>'
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", rels)
        for name, payload in sheet_payloads:
            archive.writestr(name, payload)
    return path


def generic_isotope(path: Path) -> Path:
    return write_xlsx(path, {
        "Isotopes": [
            ["(87Sr/86Sr)0", "eSr(T)", "eNd(T)"],
            [0.7031, -12.5, 4.1],
            [0.7032, -11.9, 3.8],
            [0.7030, -13.1, 4.4],
        ]
    })


def long_preamble_weight_percent(path: Path) -> Path:
    return write_xlsx(path, {
        "EPMA": [
            ["Project", "Demo project"],
            ["Owner", "Analyst"],
            ["Sample", "SYN-01"],
            ["All results in weight%"],
            ["Analysis", "SiO2", "MgO", "FeO"],
            [None, None, None, None],
            ["A-1", 51.2, 9.8, 7.1],
            ["A-2", 50.8, 10.1, 7.4],
        ]
    })


def repeated_headers(path: Path) -> Path:
    return write_xlsx(path, {
        "Mica": [
            ["Sample", "Point", "SiO2 (wt.%)", "MgO (wt.%)"],
            ["S-1", "P1", 39.1, 21.0],
            ["S-1", "P2", 39.4, 20.8],
            [None, None, None, None],
            ["Sample", "Point", "SiO2 (wt.%)", "MgO (wt.%)"],
            ["S-2", "P1", 38.8, 21.4],
            ["S-2", "P2", 39.0, 21.2],
        ]
    })


def multiple_blocks(path: Path) -> Path:
    return write_xlsx(path, {
        "EDS": [
            ["Analysis", "F (wt.%)", "Na (wt.%)", "Mg (wt.%)"],
            ["Spectrum 1", 1.2, 0.4, 10.1],
            ["Spectrum 2", 1.0, 0.5, 9.9],
            [None, None, None, None],
            ["Analysis", "La (ppm)", "Ce (ppm)", "Nd (ppm)"],
            ["Spectrum 1", 120, 250, 180],
            ["Spectrum 2", 110, 240, 175],
        ]
    })


def complementary_duplicate_blocks(path: Path) -> Path:
    return write_xlsx(path, {
        "Major and trace": [
            ["Analysis", "Sample", "SiO2 (wt.%)", "MgO (wt.%)"],
            ["A-1", "SYN-1", 50.2, 9.8],
            ["A-2", "SYN-2", 51.0, 9.2],
            [None, None, None, None],
            ["Analysis", "Sample", "La (ppm)", "Ce (ppm)"],
            ["A-1", "SYN-1", 85, 170],
            ["A-2", "SYN-2", 90, 180],
        ]
    })


def transposed_weight_percent(path: Path) -> Path:
    return write_xlsx(path, {
        "Transposed": [
            ["All results in weight%"],
            ["Field", "A-1", "A-2"],
            ["SiO2", 50.1, 51.2],
            ["MgO", 10.2, 9.8],
            ["FeO", 7.0, 7.4],
        ]
    })


def atomic_percent(path: Path) -> Path:
    return write_xlsx(path, {
        "Atomic": [
            ["atomic%"],
            ["Analysis", "O", "Si", "Mg"],
            ["Spectrum 1", 60.0, 20.0, 10.0],
            ["Spectrum 2", 59.0, 21.0, 10.5],
        ]
    })


def duplicate_field_methods(path: Path) -> Path:
    return write_xlsx(path, {
        "Mixed methods": [
            ["Analysis", "Sample", "Mineral", "Generation", "SiO2 EPMA (wt.%)", "SiO2 SIMS (wt.%)"],
            ["A-1", "SYN-1", "Phlogopite", "core", 39.2, 39.5],
            ["A-2", "SYN-1", "Phlogopite", "rim", 38.7, 39.0],
        ]
    })
