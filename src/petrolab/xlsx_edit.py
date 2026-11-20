"""Edit one plain numeric cell without reserializing the workbook."""

from contextlib import contextmanager
import ctypes
from ctypes import wintypes
from decimal import Decimal
from io import BytesIO
import math
import os
import re
from xml.etree import ElementTree
from xml.parsers import expat
from zipfile import ZipFile

from .import_preview import ImportCommandError, NS, XLSX_REL


def unsupported():
    return ImportCommandError("EDIT_XLSX_UNSUPPORTED", "Запись поддерживается для числовых ячеек XLSX в книгах без формул и цифровых подписей.")


@contextmanager
def exclusive_file(path):
    if os.name != "nt":
        raise ImportCommandError("EDIT_EXCLUSIVE_ACCESS_UNAVAILABLE", "Защищённая запись XLSX доступна в Windows.")
    import msvcrt
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    create = api.CreateFileW
    create.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                       wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    create.restype = wintypes.HANDLE
    handle = create(str(path), 0xC0000000, 0, None, 3, 0x80, None)
    if handle == wintypes.HANDLE(-1).value:
        raise ImportCommandError("EDIT_SOURCE_LOCKED", "Не удалось открыть файл для исключительной записи. Закройте его в Excel.",
                                 {"windows_error": ctypes.get_last_error()})
    try:
        descriptor = msvcrt.open_osfhandle(handle, os.O_RDWR | os.O_BINARY)
    except OSError:
        api.CloseHandle.argtypes = [wintypes.HANDLE]
        api.CloseHandle(handle)
        raise
    with os.fdopen(descriptor, "r+b") as stream:
        yield stream


def _patch_sheet(data, address, old_token, new_token):
    parser = expat.ParserCreate(namespace_separator=" ")
    tag = NS["x"] + " c"
    offset = None
    match = None

    def start(name, attributes):
        nonlocal offset
        if name == tag and attributes.get("r") == address:
            if offset is not None or match is not None or attributes.get("t", "n") != "n":
                raise unsupported()
            offset = parser.CurrentByteIndex

    def end(name):
        nonlocal match, offset
        if name != tag or offset is None:
            return
        close = data.find(b">", parser.CurrentByteIndex)
        match = (offset, close + 1)
        offset = None

    parser.StartElementHandler = start
    parser.EndElementHandler = end
    parser.Parse(data, True)
    if not match:
        raise unsupported()
    start_offset, end_offset = match
    cell = data[start_offset:end_offset]
    plain = re.fullmatch(
        rb"(<(?P<prefix>[\w.-]+:)?c(?:\s+[^<>]*)?>\s*<(?P=prefix)?v>)([^<>]+)(</(?P=prefix)?v>\s*</(?P=prefix)?c>)", cell
    )
    if not plain or plain.group(3).decode("ascii") != old_token:
        raise unsupported()
    return data[:start_offset] + plain.group(1) + new_token.encode("ascii") + plain.group(4) + data[end_offset:]


def corrected_workbook(content, sheet_name, address, old_token, new_token):
    number = r"[+-]?(?:\d+(?:\.\d+)?|\.\d+)(?:[eE][+-]?\d+)?"
    if not address or not isinstance(old_token, str) or not isinstance(new_token, str):
        raise unsupported()
    if not re.fullmatch(number, old_token) or not re.fullmatch(number, new_token):
        raise unsupported()
    value = float(new_token)
    if not math.isfinite(value) or (value == 0 and not Decimal(new_token).is_zero()):
        raise unsupported()
    with ZipFile(BytesIO(content)) as original:
        if any(entry.lower().startswith("_xmlsignatures/") for entry in original.namelist()):
            raise unsupported()
        workbook = ElementTree.fromstring(original.read("xl/workbook.xml"))
        sheet = next((item for item in workbook.findall("x:sheets/x:sheet", NS) if item.get("name") == sheet_name), None)
        if sheet is None:
            raise unsupported()
        relations = ElementTree.fromstring(original.read("xl/_rels/workbook.xml.rels"))
        relation = next((item for item in relations if item.get("Id") == sheet.get(f"{{{XLSX_REL}}}id")), None)
        if relation is None or relation.get("TargetMode") == "External":
            raise unsupported()
        target = (relation.get("Target") or "").lstrip("/")
        target = target if target.startswith("xl/") else f"xl/{target}"
        for member in original.namelist():
            if member.startswith("xl/worksheets/") and member.endswith(".xml"):
                worksheet = ElementTree.fromstring(original.read(member))
                if worksheet.find(".//x:f", NS) is not None:
                    raise unsupported()
        amended = _patch_sheet(original.read(target), address, old_token, new_token)
        result = BytesIO()
        with ZipFile(result, "w") as output:
            for info in original.infolist():
                output.writestr(info, amended if info.filename == target else original.read(info))
            output.comment = original.comment
        return result.getvalue()
