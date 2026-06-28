from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
import re
import shutil
import xml.etree.ElementTree as ET
import zipfile
from xml.etree.ElementTree import ParseError

import xlrd
import xlwt
from sqlalchemy import select
from sqlalchemy.orm import Session
from xlrd import xldate
from xlutils.copy import copy as copy_xls_workbook

from app.core.config import settings
from app.models.blank_form import (
    BLANK_STATUS_FREE,
    BLANK_STATUS_ISSUED,
    BLANK_TYPE_DRIVER_MEDICAL_CERTIFICATE,
    BlankForm,
)
from app.models.client import Client
from app.models.doctor_exam import DoctorExam
from app.models.document_journal import DocumentJournalEntry
from app.models.document_template import DocumentTemplate
from app.models.encounter import Encounter
from app.models.encounter_service import EncounterService
from app.models.generated_document import GeneratedDocument
from app.models.medical_record import MedicalRecord, MedicalRecordEntry
from app.models.service import Service
from app.schemas.document_generation import DocumentGenerateResponse
from app.services.audit import write_audit_log
from app.services.blank_forms import (
    issue_specific_blank,
    issue_next_blank,
    resolve_required_blank_type,
    reuse_blank_for_existing_document,
)
from app.services.document_context import build_document_context

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W_NS}
ET.register_namespace("w", W_NS)

PROF_EXTRACT_DOCTOR_ROWS: tuple[tuple[str, str, int], ...] = (
    ("therapist", "Терапевт", 32),
    ("psychiatrist", "Психиатр", 34),
    ("psychiatrist-narcologist", "Психиатр-нарколог", 37),
    ("neurologist", "Невролог", 39),
    ("otolaryngologist", "Отоларинголог", 41),
    ("surgeon", "Хирург", 43),
    ("gynecologist", "Гинеколог", 45),
    ("ophthalmologist", "Офтальмолог", 48),
    ("dermatologist", "Дерматовенеролог", 50),
    ("dentist", "Стоматолог", 52),
)
PROF_EXTRACT_DOCTOR_COL = 44
PROF_EXTRACT_DATE_COL = 54
PROF_EXTRACT_CONCLUSION_COL = 63
PROF_EXTRACT_SEQUENCE_COL = 42
PROF_EXTRACT_CLEARED_DOCTOR_ROWS: tuple[int, ...] = ()
PROF_EXTRACT_CLIENT_DOCTOR_FIELDS = {
    "therapist": "doctor_therapist",
    "psychiatrist": "doctor_psychiatrist",
    "psychiatrist-narcologist": "doctor_psychiatrist",
    "neurologist": "doctor_neurologist",
    "otolaryngologist": "doctor_otolaryngologist",
    "surgeon": "doctor_surgeon",
    "gynecologist": "doctor_gynecologist",
    "ophthalmologist": "doctor_ophthalmologist",
    "dermatologist": "doctor_dermatologist",
    "dentist": "doctor_stomatologist",
}
PROF_AMB_EXAM_BLOCKS: tuple[dict[str, tuple[int, int]], ...] = (
    {
        "date_cell": (1, 24),
        "title_cell": (2, 10),
        "complaints_cell": (3, 10),
        "anamnesis_cell": (4, 13),
        "objective_cell": (6, 1),
        "diagnosis_cell": (9, 1),
        "doctor_cell": (14, 11),
    },
    {
        "date_cell": (15, 24),
        "title_cell": (16, 10),
        "complaints_cell": (17, 10),
        "anamnesis_cell": (18, 13),
        "objective_cell": (20, 1),
        "diagnosis_cell": (23, 1),
        "doctor_cell": (28, 11),
    },
    {
        "date_cell": (51, 24),
        "title_cell": (52, 10),
        "complaints_cell": (53, 10),
        "anamnesis_cell": (54, 13),
        "objective_cell": (56, 1),
        "diagnosis_cell": (59, 1),
        "doctor_cell": (64, 11),
    },
    {
        "date_cell": (51, 55),
        "title_cell": (52, 41),
        "complaints_cell": (53, 41),
        "anamnesis_cell": (54, 44),
        "objective_cell": (56, 32),
        "diagnosis_cell": (59, 32),
        "doctor_cell": (64, 42),
    },
    {
        "date_cell": (66, 24),
        "title_cell": (67, 10),
        "complaints_cell": (68, 10),
        "anamnesis_cell": (69, 13),
        "objective_cell": (71, 1),
        "diagnosis_cell": (74, 1),
        "doctor_cell": (79, 11),
    },
    {
        "date_cell": (66, 55),
        "title_cell": (67, 41),
        "complaints_cell": (68, 41),
        "anamnesis_cell": (69, 44),
        "objective_cell": (71, 32),
        "diagnosis_cell": (74, 32),
        "doctor_cell": (79, 42),
    },
    {
        "date_cell": (81, 24),
        "title_cell": (82, 10),
        "complaints_cell": (83, 10),
        "anamnesis_cell": (84, 13),
        "objective_cell": (86, 1),
        "diagnosis_cell": (89, 1),
        "doctor_cell": (94, 11),
    },
    {
        "date_cell": (81, 55),
        "title_cell": (82, 41),
        "complaints_cell": (83, 41),
        "anamnesis_cell": (84, 44),
        "objective_cell": (86, 32),
        "diagnosis_cell": (89, 32),
        "doctor_cell": (94, 42),
    },
    {
        "date_cell": (96, 24),
        "title_cell": (97, 10),
        "complaints_cell": (98, 10),
        "anamnesis_cell": (99, 13),
        "objective_cell": (101, 1),
        "diagnosis_cell": (104, 1),
        "doctor_cell": (109, 11),
    },
    {
        "date_cell": (96, 55),
        "title_cell": (97, 41),
        "complaints_cell": (98, 41),
        "anamnesis_cell": (99, 44),
        "objective_cell": (101, 32),
        "diagnosis_cell": (104, 32),
        "doctor_cell": (109, 42),
    },
)


def _is_contract_template(template: DocumentTemplate) -> bool:
    text = " ".join(
        [
            str(template.name or ""),
            str(template.code or ""),
            str(template.file_name or ""),
        ]
    ).lower()
    return "договор" in text or "contract" in text


def _cleanup_contract_xml(xml_text: str) -> str:
    cleanup_patterns = [
        r"Баронина\s+Виктора\s+Евгеньевича",
        r"Баронин\s+Виктор\s+Евгеньевич",
        r"П\s*о\s*д\s*п\s*и\s*с\s*ь",
    ]
    for pattern in cleanup_patterns:
        xml_text = re.sub(pattern, "", xml_text, flags=re.IGNORECASE)
    return xml_text


def _normalize_token_key(value: str) -> str:
    return re.sub(r"\s+", "", value.replace("|", ""))


def _token_key_pattern(key: str) -> str:
    return r"\s*\.\s*".join(re.escape(part) for part in key.split("."))


def _context_token_variants(context: dict[str, str]) -> list[tuple[str, str]]:
    variants: list[tuple[str, str]] = []
    seen: set[str] = set()
    for key, value in context.items():
        normalized = _normalize_token_key(key)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        variants.append((normalized, value))
    return variants


def _normalized_context_lookup(context: dict[str, str]) -> dict[str, str]:
    return {normalized: value for normalized, value in _context_token_variants(context)}


def _has_context_bookmarks(xml_text: str, context: dict[str, str]) -> bool:
    bookmark_names = re.findall(r'w:bookmarkStart\b[^>]*\bw:name="([^"]+)"', xml_text)
    if not bookmark_names:
        return False
    context_keys = set(context.keys())
    return any(name and not name.startswith("_") and name in context_keys for name in bookmark_names)


def _replace_text_tokens(xml_text: str, context: dict[str, str]) -> str:
    for key, value in _context_token_variants(context):
        key_pattern = _token_key_pattern(key)
        patterns = [
            rf"\[\s*\|\s*{key_pattern}\s*\|\s*\]",
            rf"\[\s*{key_pattern}\s*\]",
        ]
        for pattern in patterns:
            xml_text = re.sub(pattern, value, xml_text)
    return xml_text


def _append_bookmark_value(tree: ET.ElementTree, context: dict[str, str]) -> ET.ElementTree:
    root = tree.getroot()
    for bookmark in root.findall(".//w:bookmarkStart", NS):
        bookmark_name = bookmark.attrib.get(f"{{{W_NS}}}name")
        if not bookmark_name or bookmark_name.startswith("_"):
            continue
        if bookmark_name not in context:
            continue

        parent = _find_parent(root, bookmark)
        if parent is None:
            continue

        bookmark_id = bookmark.attrib.get(f"{{{W_NS}}}id")
        value = context.get(bookmark_name, "")
        if value is None:
            value = ""

        # Remove existing text nodes until the matching bookmark end.
        removing = False
        to_remove: list[ET.Element] = []
        for child in list(parent):
            if child is bookmark:
                removing = True
                continue
            if removing and child.tag == f"{{{W_NS}}}bookmarkEnd" and child.attrib.get(f"{{{W_NS}}}id") == bookmark_id:
                break
            if removing and child.tag == f"{{{W_NS}}}r":
                to_remove.append(child)

        for node in to_remove:
            parent.remove(node)

        if value:
            run = ET.Element(f"{{{W_NS}}}r")
            text = ET.SubElement(run, f"{{{W_NS}}}t")
            text.text = value
            insert_index = list(parent).index(bookmark) + 1
            parent.insert(insert_index, run)
    return tree


def _replace_split_token_nodes(tree: ET.ElementTree, context: dict[str, str]) -> ET.ElementTree:
    root = tree.getroot()
    text_nodes = root.findall(".//w:t", NS)
    normalized_context = _normalized_context_lookup(context)
    index = 0

    while index < len(text_nodes):
        current_text = (text_nodes[index].text or "").strip()
        if current_text != "[":
            index += 1
            continue

        end_index = index + 1
        token_parts: list[str] = []
        found_end = False
        while end_index < len(text_nodes):
            part = (text_nodes[end_index].text or "").strip()
            if part == "]":
                found_end = True
                break
            token_parts.append(part)
            end_index += 1

        if not found_end:
            index += 1
            continue

        raw_token = "".join(token_parts)
        normalized_token = _normalize_token_key(raw_token)
        if normalized_token in normalized_context:
            text_nodes[index].text = normalized_context[normalized_token]
            for clear_index in range(index + 1, end_index + 1):
                text_nodes[clear_index].text = ""

        index = end_index + 1

    return tree


def _replace_text_node_tokens(tree: ET.ElementTree, context: dict[str, str]) -> ET.ElementTree:
    variants = _context_token_variants(context)
    for text_node in tree.getroot().findall(".//w:t", NS):
        text = text_node.text or ""
        if "[" not in text:
            continue
        for key, value in variants:
            key_pattern = _token_key_pattern(key)
            text = re.sub(rf"\[\s*\|\s*{key_pattern}\s*\|\s*\]", value, text)
            text = re.sub(rf"\[\s*{key_pattern}\s*\]", value, text)
        text_node.text = text
    return tree


def _replace_paragraph_tokens(tree: ET.ElementTree, context: dict[str, str]) -> ET.ElementTree:
    variants = _context_token_variants(context)
    for paragraph in tree.getroot().findall(".//w:p", NS):
        text_nodes = paragraph.findall(".//w:t", NS)
        if not text_nodes:
            continue
        text = "".join(node.text or "" for node in text_nodes)
        if "[" not in text:
            continue
        replaced = text
        for key, value in variants:
            key_pattern = _token_key_pattern(key)
            replaced = re.sub(rf"\[\s*\|\s*{key_pattern}\s*\|\s*\]", value, replaced)
            replaced = re.sub(rf"\[\s*{key_pattern}\s*\]", value, replaced)
        if replaced == text:
            continue
        text_nodes[0].text = replaced
        for node in text_nodes[1:]:
            node.text = ""
    return tree


def _find_parent(root: ET.Element, node: ET.Element) -> ET.Element | None:
    for parent in root.iter():
        for child in list(parent):
            if child is node:
                return parent
    return None


def _set_cell_text(cell: ET.Element, value: str) -> None:
    text_nodes = cell.findall(".//w:t", NS)
    if text_nodes:
        text_nodes[0].text = value
        for node in text_nodes[1:]:
            node.text = ""
        return

    paragraph = cell.find("w:p", NS)
    if paragraph is None:
        paragraph = ET.SubElement(cell, f"{{{W_NS}}}p")
    run = paragraph.find("w:r", NS)
    if run is None:
        run = ET.SubElement(paragraph, f"{{{W_NS}}}r")
    text = ET.SubElement(run, f"{{{W_NS}}}t")
    text.text = value


def _expand_service_rows(tree: ET.ElementTree, service_rows: list[dict[str, str]]) -> ET.ElementTree:
    root = tree.getroot()
    token = "qdfOrderServices_Ordinal_Service_Quantity_ServiceDate"
    for table in root.findall(".//w:tbl", NS):
        rows = table.findall("w:tr", NS)
        for row in rows:
            if len(row.findall("w:tc", NS)) < 4:
                continue
            row_text = "".join(text.text or "" for text in row.findall(".//w:t", NS))
            if token not in row_text:
                continue

            row_index = list(table).index(row)
            table.remove(row)
            if not service_rows:
                return tree
            for offset, item in enumerate(service_rows):
                new_row = ET.fromstring(ET.tostring(row, encoding="utf-8"))
                cells = new_row.findall("w:tc", NS)
                values = [
                    item.get("ordinal", ""),
                    item.get("service", ""),
                    item.get("quantity", "1"),
                    item.get("date", ""),
                ]
                for cell, value in zip(cells, values):
                    _set_cell_text(cell, value)
                table.insert(row_index + offset, new_row)
            return tree

    return tree


def _generate_docx(
    template_path: Path,
    output_path: Path,
    context: dict[str, str],
    service_rows: list[dict[str, str]] | None = None,
    cleanup_xml: bool = False,
) -> None:
    with zipfile.ZipFile(template_path, "r") as source_zip:
        with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as target_zip:
            for item in source_zip.infolist():
                file_bytes = source_zip.read(item.filename)
                if item.filename == "word/document.xml":
                    xml_text = file_bytes.decode("utf-8")
                    xml_text = _replace_text_tokens(xml_text, context)
                    if cleanup_xml:
                        xml_text = _cleanup_contract_xml(xml_text)
                    needs_tree_pass = (
                        "[" in xml_text
                        or _has_context_bookmarks(xml_text, context)
                        or (
                            bool(service_rows)
                            and "qdfOrderServices_Ordinal_Service_Quantity_ServiceDate" in xml_text
                        )
                    )
                    if needs_tree_pass:
                        try:
                            tree = ET.ElementTree(ET.fromstring(xml_text))
                            tree = _replace_paragraph_tokens(tree, context)
                            tree = _replace_text_node_tokens(tree, context)
                            tree = _replace_split_token_nodes(tree, context)
                            tree = _append_bookmark_value(tree, context)
                            tree = _expand_service_rows(tree, service_rows or [])
                            file_bytes = ET.tostring(tree.getroot(), encoding="utf-8", xml_declaration=True)
                        except ParseError:
                            # Some client templates contain non-standard Word XML fragments.
                            # In that case we still keep token replacement instead of failing generation.
                            file_bytes = xml_text.encode("utf-8")
                    else:
                        file_bytes = xml_text.encode("utf-8")
                target_zip.writestr(item, file_bytes)


def _generate_xml(template_path: Path, output_path: Path, context: dict[str, str]) -> None:
    xml_text = template_path.read_text(encoding="utf-8", errors="ignore")
    xml_text = _replace_text_tokens(xml_text, context)
    for key, value in context.items():
        xml_text = xml_text.replace(f"{{{{{key}}}}}", value)
    output_path.write_text(xml_text, encoding="utf-8")


def _write_xls_cell(target_sheet, source_sheet, row_index: int, col_index: int, value: object, style=None) -> None:
    existing_xf_idx = None
    existing_row = target_sheet._Worksheet__rows.get(row_index)
    if existing_row is not None:
        existing_cell = existing_row._Row__cells.get(col_index)
        if existing_cell is not None:
            existing_xf_idx = getattr(existing_cell, "xf_idx", None)

    if style is not None:
        target_sheet.write(row_index, col_index, value, style)
        return

    target_sheet.write(row_index, col_index, value)
    row = target_sheet._Worksheet__rows.get(row_index)
    if row is None:
        return
    cell = row._Row__cells.get(col_index)
    if cell is None:
        return
    if existing_xf_idx is not None:
        cell.xf_idx = existing_xf_idx
        return
    try:
        cell.xf_idx = source_sheet.cell_xf_index(row_index, col_index)
    except IndexError:
        # Some legacy sheets have blank trailing rows without style metadata.
        # In that case we keep the written value without cloning formatting.
        return


def _xls_cell_style(
    source_book,
    source_sheet,
    row_index: int,
    col_index: int,
    *,
    shrink_to_fit: bool | None = None,
    num_format_str: str | None = None,
):
    xf = source_book.xf_list[source_sheet.cell_xf_index(row_index, col_index)]
    style = xlwt.XFStyle()

    if num_format_str is not None:
        style.num_format_str = num_format_str
    else:
        try:
            style.num_format_str = source_book.format_map[xf.format_key].format_str
        except KeyError:
            pass

    source_font = source_book.font_list[xf.font_index]
    font = xlwt.Font()
    font.height = source_font.height
    font.italic = bool(source_font.italic)
    font.struck_out = bool(source_font.struck_out)
    font.outline = bool(source_font.outline)
    font.shadow = bool(source_font.shadow)
    font.colour_index = source_font.colour_index
    font.bold = bool(source_font.bold)
    font._weight = source_font.weight
    font.escapement = source_font.escapement
    font.underline = source_font.underline_type
    font.family = source_font.family
    font.charset = source_font.character_set
    font.name = source_font.name
    style.font = font

    source_alignment = xf.alignment
    alignment = xlwt.Alignment()
    alignment.horz = source_alignment.hor_align
    alignment.vert = source_alignment.vert_align
    alignment.dire = source_alignment.text_direction
    alignment.rota = source_alignment.rotation
    alignment.wrap = source_alignment.text_wrapped
    should_shrink = source_alignment.shrink_to_fit if shrink_to_fit is None else shrink_to_fit
    alignment.shri = xlwt.Alignment.SHRINK_TO_FIT if should_shrink else 0
    alignment.inde = source_alignment.indent_level
    style.alignment = alignment

    source_border = xf.border
    borders = xlwt.Borders()
    borders.left = source_border.left_line_style
    borders.right = source_border.right_line_style
    borders.top = source_border.top_line_style
    borders.bottom = source_border.bottom_line_style
    borders.diag = source_border.diag_line_style
    borders.left_colour = source_border.left_colour_index
    borders.right_colour = source_border.right_colour_index
    borders.top_colour = source_border.top_colour_index
    borders.bottom_colour = source_border.bottom_colour_index
    borders.diag_colour = source_border.diag_colour_index
    borders.need_diag1 = source_border.diag_down
    borders.need_diag2 = source_border.diag_up
    style.borders = borders

    source_background = xf.background
    pattern = xlwt.Pattern()
    pattern.pattern = source_background.fill_pattern
    pattern.pattern_fore_colour = source_background.pattern_colour_index
    pattern.pattern_back_colour = source_background.background_colour_index
    style.pattern = pattern

    source_protection = xf.protection
    protection = xlwt.Protection()
    protection.cell_locked = source_protection.cell_locked
    protection.formula_hidden = source_protection.formula_hidden
    style.protection = protection

    return style


def _xls_shrink_to_fit_style(source_book, source_sheet, row_index: int, col_index: int):
    return _xls_cell_style(source_book, source_sheet, row_index, col_index, shrink_to_fit=True)


def _copy_xls_target_cell_style(target_sheet, target_row: int, target_col: int, source_row: int, source_col: int) -> None:
    target_row_obj = target_sheet._Worksheet__rows.get(target_row)
    if target_row_obj is None:
        return
    target_cell = target_row_obj._Row__cells.get(target_col)
    if target_cell is None:
        return

    source_row_obj = target_sheet._Worksheet__rows.get(source_row)
    if source_row_obj is None:
        return
    source_cell = source_row_obj._Row__cells.get(source_col)
    if source_cell is None:
        return
    source_xf_idx = getattr(source_cell, "xf_idx", None)
    if source_xf_idx is not None:
        target_cell.xf_idx = source_xf_idx


def _xls_excel_date(value: date | datetime | str | None) -> float | str:
    if value in (None, ""):
        return ""
    if isinstance(value, datetime):
        value = value.date()
    if not isinstance(value, date):
        return str(value)
    if value <= date(1900, 1, 1):
        return ""
    if value < date(1900, 3, 1):
        return value.strftime("%d.%m.%y")
    return xldate.xldate_from_date_tuple((value.year, value.month, value.day), 0)


def _prof_xls_display_date(value: date | datetime | str | None) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, date):
        return value.strftime("%d.%m.%y")
    return str(value)


def _exam_field(fields: dict, *keys: str) -> str:
    lowered = {str(key).lower(): value for key, value in fields.items()}
    for key in keys:
        value = fields.get(key)
        if value in (None, ""):
            value = lowered.get(key.lower())
        if value not in (None, ""):
            return str(value).strip()
    return ""


def _build_exam_export(exam: DoctorExam | None) -> dict[str, object]:
    if exam is None:
        return {
            "date": "",
            "title": "",
            "complaints": "",
            "anamnesis": "",
            "objective": "",
            "diagnosis": "",
            "doctor": "",
        }

    fields = exam.fields_json or {}
    result_text = str(exam.result_text or "").strip()
    diagnosis = (
        str(exam.diagnosis or "").strip()
        or _exam_field(fields, "diagnosis", "diagnosisShort", "diagnosisText", "diagnoz", "conclusion")
        or result_text
    )
    objective = (
        _exam_field(
            fields,
            "objective",
            "objectiveData",
            "objectiveText",
            "status",
            "statusLocalis",
            "inspection",
            "exam",
            "result",
        )
        or result_text
    )
    return {
        "date": exam.completed_at.date() if exam.completed_at else "",
        "title": _exam_field(fields, "conclusionTitle", "title", "caption"),
        "complaints": _exam_field(fields, "complaints", "complaint", "complaintsText"),
        "anamnesis": _exam_field(fields, "anamnesis", "anamnesisText", "history", "anamnesisVitae"),
        "objective": objective,
        "diagnosis": diagnosis,
        "doctor": str(exam.doctor_name or "").strip(),
    }


def _prof_extract_exam_date(exam: DoctorExam, encounter: Encounter | None) -> object:
    if exam.completed_at:
        return exam.completed_at.date()
    if encounter is not None:
        return encounter.encounter_date
    return ""


def _prof_extract_exam_conclusion(exam: DoctorExam) -> str:
    fields = exam.fields_json or {}
    conclusion = _exam_field(fields, "conclusion", "result", "decision", "fit")
    if not conclusion:
        conclusion = str(exam.result_text or exam.diagnosis or "").strip()

    normalized = conclusion.strip().lower()
    if normalized == "годен":
        return "годен"
    if normalized == "не годен":
        return "не годен"
    return conclusion


def _prof_extract_doctor_name(client: Client | None, role_id: str, exam_data: dict[str, object]) -> str:
    client_field = PROF_EXTRACT_CLIENT_DOCTOR_FIELDS.get(role_id)
    if client is not None and client_field:
        client_value = str(getattr(client, client_field, "") or "").strip()
        if client_value:
            return client_value
    return str(exam_data.get("doctor") or "").strip()


def _exam_export_with_client_doctor(
    exam: DoctorExam | None,
    client: Client | None,
    role_id: str,
) -> dict[str, object]:
    data = _build_exam_export(exam)
    data["doctor"] = _prof_extract_doctor_name(client, role_id, data)
    return data


def _exam_conclusion_line_for_role(
    exam: DoctorExam | None,
    client: Client | None,
    role_id: str,
    fallback: str = "Противопоказания отсутствуют",
) -> str:
    data = _exam_export_with_client_doctor(exam, client, role_id)
    doctor = str(data.get("doctor") or "").strip()
    conclusion = _first_non_empty(data.get("diagnosis"), data.get("objective"), data.get("title"), fallback)
    return " ".join(part for part in [doctor, conclusion] if part).strip()


def _prof_extract_doctor_row_values(
    exams_by_role: dict[str, DoctorExam],
    encounter: Encounter | None,
    client: Client | None = None,
) -> list[tuple[int, str, object, str]]:
    rows: list[tuple[int, str, object, str]] = []
    row_indices = [row_index for _, _, row_index in PROF_EXTRACT_DOCTOR_ROWS]
    for role_id, specialty, row_index in PROF_EXTRACT_DOCTOR_ROWS:
        exam = exams_by_role.get(role_id)
        if exam is None or not exam.is_completed:
            continue

        exam_data = _build_exam_export(exam)
        doctor_name = _prof_extract_doctor_name(client, role_id, exam_data)
        doctor_line = " ".join(part for part in [specialty, doctor_name] if part).strip()
        target_row_index = row_indices[len(rows)]
        rows.append(
            (
                target_row_index,
                doctor_line,
                _prof_extract_exam_date(exam, encounter),
                _prof_extract_exam_conclusion(exam),
            )
        )
    return rows


def _prof_amb_exam_block_values(
    exams_by_role: dict[str, DoctorExam],
    encounter: Encounter | None,
    client: Client | None = None,
) -> list[tuple[str, dict[str, object]]]:
    blocks: list[tuple[str, dict[str, object]]] = []
    for role_id, specialty, _ in PROF_EXTRACT_DOCTOR_ROWS:
        exam = exams_by_role.get(role_id)
        if exam is None or not exam.is_completed:
            continue

        data = _build_exam_export(exam)
        data["doctor"] = _prof_extract_doctor_name(client, role_id, data)
        if not data.get("date"):
            data["date"] = _prof_extract_exam_date(exam, encounter)
        if not str(data.get("title") or "").strip():
            data["title"] = f"Врач {specialty.lower()}"
        blocks.append((role_id, data))
    return blocks


def _is_rural_address(*parts: str) -> bool:
    text = " ".join(part for part in parts if part).lower()
    return bool(re.search(r"\b(пос|пгт|село|дер|деревня|снт|рп|гп)\b", text))


def _split_policy(policy: str) -> tuple[str, str]:
    cleaned = re.sub(r"\s+", " ", str(policy or "").strip())
    if not cleaned:
        return "", ""
    parts = cleaned.split(" ", 1)
    if len(parts) == 1:
        digits = re.sub(r"\D", "", parts[0])
        if len(digits) > 10:
            return digits[:-10], digits[-10:]
        return "", parts[0]
    return parts[0], parts[1]


def _split_document(series: str, number: str) -> tuple[str, str]:
    merged = " ".join(part for part in [str(series or "").strip(), str(number or "").strip()] if part).strip()
    digits = re.sub(r"\D", "", merged)
    if len(digits) >= 10:
        return digits[:4], digits[4:10]
    return str(series or "").strip(), str(number or "").strip()


def _clear_xls_cells(target_sheet, source_sheet, coordinates: list[tuple[int, int]]) -> None:
    for row_index, col_index in coordinates:
        _write_xls_cell(target_sheet, source_sheet, row_index, col_index, "")


def _prof_amb_doctor_name_range(doctor_cell: tuple[int, int]) -> tuple[int, int, int]:
    row_index, col_index = doctor_cell
    end_col = 62 if col_index >= 32 else 31
    return row_index, col_index, end_col


def _fill_exam_block(
    target_sheet,
    source_sheet,
    data: dict[str, object],
    *,
    source_book=None,
    date_cell: tuple[int, int],
    title_cell: tuple[int, int],
    complaints_cell: tuple[int, int],
    anamnesis_cell: tuple[int, int],
    objective_cell: tuple[int, int],
    diagnosis_cell: tuple[int, int],
    doctor_cell: tuple[int, int],
) -> None:
    date_style = (
        _xls_cell_style(source_book, source_sheet, *date_cell, shrink_to_fit=False, num_format_str="@")
        if source_book is not None
        else None
    )
    _write_xls_cell(target_sheet, source_sheet, *date_cell, _prof_xls_display_date(data.get("date")), date_style)
    _write_xls_cell(target_sheet, source_sheet, *title_cell, str(data.get("title") or ""))
    _write_xls_cell(target_sheet, source_sheet, *complaints_cell, str(data.get("complaints") or ""))
    _write_xls_cell(target_sheet, source_sheet, *anamnesis_cell, str(data.get("anamnesis") or ""))
    _write_xls_cell(target_sheet, source_sheet, *objective_cell, str(data.get("objective") or ""))
    _write_xls_cell(target_sheet, source_sheet, *diagnosis_cell, str(data.get("diagnosis") or ""))
    doctor_value = str(data.get("doctor") or "").strip()
    doctor_row, doctor_start_col, doctor_end_col = _prof_amb_doctor_name_range(doctor_cell)
    doctor_style = (
        _xls_cell_style(source_book, source_sheet, *doctor_cell, shrink_to_fit=False)
        if source_book is not None
        else None
    )
    if doctor_value and source_book is not None and doctor_end_col > doctor_start_col:
        target_sheet.write_merge(doctor_row, doctor_row, doctor_start_col, doctor_end_col, doctor_value, doctor_style)
    elif doctor_value:
        _write_xls_cell(target_sheet, source_sheet, *doctor_cell, doctor_value, doctor_style)
    else:
        _clear_xls_cells(
            target_sheet,
            source_sheet,
            [(doctor_row, col_index) for col_index in range(doctor_start_col, doctor_end_col + 1)],
        )


def _clear_prof_amb_exam_block(target_sheet, source_sheet, block: dict[str, tuple[int, int]]) -> None:
    date_cell = block["date_cell"]
    title_cell = block["title_cell"]
    doctor_cell = block["doctor_cell"]
    label_col = max(0, title_cell[1] - 9)
    end_col = min(source_sheet.ncols, label_col + 31)
    coordinates: set[tuple[int, int]] = set(block.values())
    doctor_row, doctor_start_col, doctor_end_col = _prof_amb_doctor_name_range(doctor_cell)
    coordinates.update((doctor_row, col_index) for col_index in range(doctor_start_col, doctor_end_col + 1))
    for row_index in range(date_cell[0], doctor_cell[0] + 1):
        for col_index in range(label_col, end_col):
            if source_sheet.cell_value(row_index, col_index) not in ("", None):
                coordinates.add((row_index, col_index))
    _clear_xls_cells(target_sheet, source_sheet, sorted(coordinates))


def _write_xls_pairs(target_sheet, source_sheet, pairs: list[tuple[tuple[int, int], object]]) -> None:
    for (row_index, col_index), value in pairs:
        _write_xls_cell(target_sheet, source_sheet, row_index, col_index, value)


def _normalize_xls_auto_label(value: object) -> str:
    text = str(value or "").strip().lower().replace("ё", "е")
    return re.sub(r"[^0-9a-zа-я]+", " ", text).strip()


def _iter_xls_auto_markers(source_book) -> list[tuple[int, object, int, int, str]]:
    markers: list[tuple[int, object, int, int, str]] = []
    for sheet_index, source_sheet in enumerate(source_book.sheets()):
        seen_merges: set[tuple[int, int, int, int]] = set()
        for row_index in range(source_sheet.nrows):
            for col_index in range(source_sheet.ncols):
                try:
                    xf_index = source_sheet.cell_xf_index(row_index, col_index)
                    bg_index = source_book.xf_list[xf_index].background.pattern_colour_index
                except IndexError:
                    continue
                if bg_index != 13:
                    continue

                merge = next(
                    (
                        item
                        for item in source_sheet.merged_cells
                        if item[0] <= row_index < item[1] and item[2] <= col_index < item[3]
                    ),
                    None,
                )
                if merge is not None:
                    if merge in seen_merges:
                        continue
                    seen_merges.add(merge)
                    row_index, col_index = merge[0], merge[2]

                label = _normalize_xls_auto_label(source_sheet.cell_value(row_index, col_index))
                if "авто" in label:
                    markers.append((sheet_index, source_sheet, row_index, col_index, label))
    return markers


def _xls_auto_marker_values(
    context: dict[str, str],
    client: Client,
    encounter: Encounter | None,
    exams_by_role: dict[str, DoctorExam],
) -> list[tuple[tuple[str, ...], object]]:
    issue_date = encounter.encounter_date if encounter else date.today()
    therapist = _exam_export_with_client_doctor(exams_by_role.get("therapist"), client, "therapist")
    chairman = _build_exam_export(exams_by_role.get("chairman"))
    return [
        (("терапевт",), _exam_conclusion_line_for_role(exams_by_role.get("therapist"), client, "therapist")),
        (("офтальмолог", "окулист"), _exam_conclusion_line_for_role(exams_by_role.get("ophthalmologist"), client, "ophthalmologist")),
        (("невролог",), _exam_conclusion_line_for_role(exams_by_role.get("neurologist"), client, "neurologist")),
        (("лор", "отоларинголог"), _exam_conclusion_line_for_role(exams_by_role.get("otolaryngologist"), client, "otolaryngologist")),
        (("хирург",), _exam_conclusion_line_for_role(exams_by_role.get("surgeon"), client, "surgeon")),
        (("психиатр нарколог", "психиатр-нарколог", "нарколог"), _exam_conclusion_line_for_role(exams_by_role.get("psychiatrist-narcologist"), client, "psychiatrist-narcologist")),
        (("психиатр",), _exam_conclusion_line_for_role(exams_by_role.get("psychiatrist"), client, "psychiatrist")),
        (("дермат",), _exam_conclusion_line_for_role(exams_by_role.get("dermatologist"), client, "dermatologist")),
        (("гинеколог",), _exam_conclusion_line_for_role(exams_by_role.get("gynecologist"), client, "gynecologist")),
        (("председатель", "глав врач", "главный врач", "подписант"), _first_non_empty(chairman.get("doctor"), therapist.get("doctor"), context.get("Doctor"))),
        (("врач",), _first_non_empty(therapist.get("doctor"), context.get("Doctor"))),
        (("фио", "пациент"), context.get("ClientCalc", "")),
        (("дата рождения", "др"), _xls_excel_date(client.birth_date)),
        (("возраст",), _age_at_date(client.birth_date, issue_date)),
        (("пол",), context.get("SexCalc", "")),
        (("адрес",), context.get("AddressCalc", "")),
        (("телефон",), context.get("Phone", "")),
        (("снилс",), context.get("SNILS", "")),
        (("паспорт серия", "серия"), context.get("DocumentSeries", "")),
        (("паспорт номер", "номер паспорта"), context.get("DocumentNumber", "")),
        (("кем выдан",), context.get("WhoGive", "")),
        (("дата выдачи",), context.get("DocumentDate", "")),
        (("организация", "место работы", "работа"), context.get("CompanyName", "")),
        (("должность", "профессия"), _first_non_empty(context.get("Post"), context.get("PositionApplied"))),
        (("услуга", "услуги"), context.get("Services", "")),
        (("номер бланка", "бланк"), context.get("BlankFullNumber") or context.get("BlankNumber", "")),
        (("номер",), context.get("ReferenceNumber", "")),
        (("дата",), _xls_excel_date(issue_date)),
        (("заключение", "итог"), context.get("Conclusion", "")),
    ]


def _apply_xls_auto_markers(
    source_book,
    target_book,
    context: dict[str, str],
    client: Client,
    encounter: Encounter | None,
    exams_by_role: dict[str, DoctorExam],
) -> None:
    values = _xls_auto_marker_values(context, client, encounter, exams_by_role)
    for sheet_index, source_sheet, row_index, col_index, label in _iter_xls_auto_markers(source_book):
        value = None
        for aliases, candidate in values:
            if any(alias in label for alias in aliases):
                value = candidate
                break
        if value is None:
            continue
        target_sheet = target_book.get_sheet(sheet_index)
        _write_xls_cell(target_sheet, source_sheet, row_index, col_index, value)


def _exam_map(exams: list[DoctorExam]) -> dict[str, DoctorExam]:
    result: dict[str, DoctorExam] = {}
    for exam in exams:
        role_key = str(exam.doctor_role_id or "").strip().lower()
        result.setdefault(role_key, exam)
    return result


def _first_non_empty(*values: object) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _exam_conclusion_line(exam: DoctorExam | None, fallback: str = "Противопоказания отсутствуют") -> str:
    data = _build_exam_export(exam)
    doctor = str(data.get("doctor") or "").strip()
    conclusion = _first_non_empty(data.get("diagnosis"), data.get("objective"), data.get("title"), fallback)
    return " ".join(part for part in [doctor, conclusion] if part).strip()


def _age_at_date(birth_date: date | None, on_date: date | None) -> str:
    if birth_date is None:
        return ""
    check_date = on_date or date.today()
    years = check_date.year - birth_date.year - ((check_date.month, check_date.day) < (birth_date.month, birth_date.day))
    return str(years)


def _sheet_pair(source_book, target_book, sheet_name: str):
    if sheet_name not in source_book.sheet_names():
        return None, None, None
    index = source_book.sheet_names().index(sheet_name)
    return source_book.sheet_by_index(index), target_book.get_sheet(index), index


def _sheet_pair_any(source_book, target_book, sheet_names: tuple[str, ...]):
    for sheet_name in sheet_names:
        source_sheet, target_sheet, index = _sheet_pair(source_book, target_book, sheet_name)
        if source_sheet is not None and target_sheet is not None:
            return source_sheet, target_sheet, index
    return None, None, None


def _fill_contract_xls_sheet(
    source_sheet,
    target_sheet,
    context: dict[str, str],
    client: Client,
    encounter: Encounter | None,
    runtime_values: dict[str, object],
) -> None:
    service_rows = runtime_values.get("service_rows", [])
    first_service = service_rows[0]["service"] if service_rows else context.get("Services", "")
    quantity = service_rows[0]["quantity"] if service_rows else "1"
    total_amount = str(encounter.total_amount or "") if encounter else ""
    doctor_name = context.get("UserName", "")
    full_name = context.get("ClientCalc", "")
    birth_date = context.get("BirthDateCalc", "")
    address = context.get("AddressCalc", "")
    passport_summary = (
        f"Паспорт РФ Серия:{context.get('DocumentSeries', '')} "
        f"Номер:{context.get('DocumentNumber', '')} "
        f"Кем выдан: {context.get('WhoGive', '')} - {context.get('DocumentDate', '')}"
    ).strip()
    _write_xls_pairs(
        target_sheet,
        source_sheet,
        [
            ((6, 2), f"Я, {full_name}, {birth_date} г. рождения,"),
            ((8, 6), address),
            ((8, 33), f"/ {doctor_name}" if doctor_name else ""),
            ((12, 34), context.get("ReferenceNumber", "")),
            ((14, 37), _xls_excel_date(encounter.encounter_date if encounter else date.today())),
            ((21, 1), f"{full_name} ( {context.get('Phone', '')} )"),
            ((24, 1), full_name),
            ((27, 16), _xls_excel_date(encounter.encounter_date if encounter else date.today())),
            ((31, 1), f"Я, {full_name}, {birth_date} г. рождения, зарегистрированная по адресу:"),
            ((32, 1), address),
            ((33, 1), passport_summary),
            ((33, 23), first_service),
            ((33, 37), quantity),
            ((33, 39), total_amount),
            ((37, 28), f"/ {full_name}" if full_name else ""),
            ((48, 1), f"Настоящее согласие дано мной {context.get('VisitDate', '')} и действует бессрочно."),
            ((55, 1), full_name),
            ((82, 23), total_amount),
            ((82, 33), f"/ {doctor_name}" if doctor_name else ""),
            ((86, 23), total_amount),
            ((86, 33), f"/ {doctor_name}" if doctor_name else ""),
            ((89, 33), f"Ф.И.О.: {full_name}" if full_name else ""),
            ((91, 33), f"Адрес места жительства: {address}" if address else ""),
            ((93, 35), client.document_type or "Паспорт РФ"),
            ((94, 35), context.get("DocumentSeries", "")),
            ((95, 35), context.get("DocumentNumber", "")),
            ((96, 33), f"Кем выдан: {context.get('WhoGive', '')}".strip()),
            ((99, 35), _xls_excel_date(client.document_issued_date)),
            ((100, 35), context.get("Phone", "")),
            ((106, 36), f"/ {full_name}" if full_name else ""),
        ],
    )


def _fill_086_xls_sheet(
    source_sheet,
    target_sheet,
    context: dict[str, str],
    client: Client,
    encounter: Encounter | None,
    exams_by_role: dict[str, DoctorExam],
) -> None:
    issue_date = encounter.encounter_date if encounter else date.today()
    _write_xls_pairs(
        target_sheet,
        source_sheet,
        [
            ((10, 12), context.get("ReferenceNumber", "")),
            ((13, 5), context.get("ClientCalc", "")),
            ((14, 5), _xls_excel_date(client.birth_date)),
            ((15, 10), context.get("SubjectCalc", "")),
            ((16, 3), context.get("DistrictCalc", "")),
            ((17, 4), context.get("CityCalc", "")),
            ((17, 9), " ".join(
                part
                for part in [
                    context.get("StreetCalc", ""),
                    context.get("HouseNumberCalc", ""),
                    context.get("ApartmentNumberCalc", ""),
                ]
                if part
            )),
            ((18, 5), _first_non_empty(context.get("WorkPlace"), context.get("CompanyName"), "по месту требования")),
            ((23, 4), _first_non_empty(_build_exam_export(exams_by_role.get("therapist")).get("diagnosis"), "Дз: практически здоров")),
            ((23, 15), _build_exam_export(exams_by_role.get("therapist")).get("doctor", "")),
            ((24, 4), _build_exam_export(exams_by_role.get("surgeon")).get("diagnosis", "")),
            ((24, 15), _build_exam_export(exams_by_role.get("surgeon")).get("doctor", "")),
            ((25, 4), _build_exam_export(exams_by_role.get("neurologist")).get("diagnosis", "")),
            ((25, 15), _build_exam_export(exams_by_role.get("neurologist")).get("doctor", "")),
            ((27, 5), _build_exam_export(exams_by_role.get("otolaryngologist")).get("diagnosis", "")),
            ((27, 15), _build_exam_export(exams_by_role.get("otolaryngologist")).get("doctor", "")),
            ((44, 1), context.get("Conclusion", "")),
            ((48, 1), _xls_excel_date(issue_date)),
            ((50, 12), _first_non_empty(_build_exam_export(exams_by_role.get("therapist")).get("doctor"), context.get("Doctor", ""))),
            ((53, 12), _first_non_empty(_build_exam_export(exams_by_role.get("chairman")).get("doctor"), _build_exam_export(exams_by_role.get("therapist")).get("doctor"), context.get("Doctor", ""))),
        ],
    )


def _fill_eeg_xls_sheet(
    source_sheet,
    target_sheet,
    context: dict[str, str],
    client: Client,
    encounter: Encounter | None,
    exams: list[DoctorExam],
) -> None:
    eeg_exam = next((exam for exam in exams if "ээг" in f"{exam.result_text or ''} {exam.diagnosis or ''}".lower()), None)
    eeg_data = _build_exam_export(eeg_exam)
    doctor_name = _first_non_empty(eeg_data.get("doctor"), context.get("Doctor"))
    _write_xls_pairs(
        target_sheet,
        source_sheet,
        [
            ((9, 8), _xls_excel_date(encounter.encounter_date if encounter else date.today())),
            ((11, 8), context.get("ClientCalc", "")),
            ((13, 8), _age_at_date(client.birth_date, encounter.encounter_date if encounter else None)),
            ((15, 8), context.get("CardNumber", "") or context.get("ReferenceNumber", "")),
            ((17, 8), doctor_name),
        ],
    )


def _fill_chod_xls_sheet(
    source_sheet,
    target_sheet,
    context: dict[str, str],
    encounter: Encounter | None,
) -> None:
    issue_date = encounter.encounter_date if encounter else date.today()
    _write_xls_pairs(
        target_sheet,
        source_sheet,
        [
            ((17, 15), context.get("BlankNumber", "") or context.get("ReferenceNumber", "")),
            ((20, 3), context.get("ClientCalc", "")),
            ((21, 11), issue_date.day),
            ((21, 20), issue_date.year),
            ((23, 3), context.get("SubjectCalc", "")),
            ((24, 5), context.get("DistrictCalc", "")),
            ((25, 4), context.get("CityCalc", "")),
            ((27, 5), context.get("StreetCalc", "")),
            ((28, 5), " ".join(part for part in [context.get("HouseNumberCalc", ""), context.get("ApartmentNumberCalc", "")] if part)),
            ((30, 16), _xls_excel_date(issue_date)),
            ((36, 12), context.get("Doctor", "")),
        ],
    )


def _restriction_text(value: object) -> str:
    text = str(value or "").strip().lower()
    if not text or text in {"0", "нет", "false", "no", "не установлено"}:
        return "не установлено"
    return "установлено"


def _xls_blank_or_dash(value: object) -> str:
    text = str(value or "").strip()
    return text or "-"


def _driver_exam_line(exam: DoctorExam | None, fallback: str = "Противопоказания отсутствуют") -> str:
    if exam is None:
        return fallback
    data = _build_exam_export(exam)
    doctor = str(data.get("doctor") or "").strip()
    if not doctor:
        return fallback
    conclusion = _first_non_empty(
        data.get("diagnosis"),
        data.get("objective"),
        data.get("title"),
        "Противопоказания отсутствуют",
    )
    return " ".join(part for part in [doctor, conclusion] if part).strip()


def _driver_auxiliary_line(context: dict[str, str], key: str, fallback: str = "Не установлено") -> str:
    value = str(context.get(key) or "").strip()
    return value or fallback


DRIVER_XLS_CATEGORY_KEYS = ("A", "B", "C", "D", "BE", "CE", "DE", "Tm", "Tb", "M", "A1", "B1", "C1", "D1", "C1E", "D1E")
DRIVER_XLS_CATEGORY_CELLS_LEFT = (
    (10, 2),
    (10, 4),
    (10, 6),
    (10, 8),
    (10, 10),
    (10, 12),
    (10, 14),
    (10, 16),
    (10, 18),
    (10, 20),
    (10, 22),
    (10, 24),
    (10, 26),
    (10, 28),
    (10, 30),
    (10, 32),
)
DRIVER_XLS_CATEGORY_CELLS_RIGHT = (
    (10, 35),
    (10, 37),
    (10, 39),
    (10, 41),
    (10, 43),
    (10, 45),
    (10, 47),
    (10, 49),
    (10, 51),
    (10, 53),
    (10, 55),
    (10, 57),
    (10, 59),
    (10, 61),
    (10, 63),
    (10, 65),
)
DRIVER_CATEGORY_FIELD_KEYS = {
    "A": "categoryA",
    "B": "categoryB",
    "C": "categoryC",
    "D": "categoryD",
    "BE": "categoryBE",
    "CE": "categoryCE",
    "DE": "categoryDE",
    "Tm": "categoryTram",
    "Tb": "categoryTrolleybus",
    "M": "categoryM",
    "A1": "categoryA1",
    "B1": "categoryB1",
    "C1": "categoryC1",
    "D1": "categoryD1",
    "C1E": "categoryC1E",
    "D1E": "categoryD1E",
}
DRIVER_XLS_FRONT_SHEET_NAMES = ("Водительская Лицевая", "Вод.Лиц22")
DRIVER_XLS_BACK_SHEET_NAMES = ("Водительская Оборотная", "Вод.Об22", "Вод.Оборот")
DRIVER_CATEGORY_LEGACY_ALIASES = {
    "A1": "1A",
    "B1": "1B",
    "C1": "1C",
    "D1": "1D",
    "C1E": "1CE",
    "D1E": "1DE",
}
DRIVER_XML_CATEGORY_TOKENS = {
    "A": ("ACalc", "CategoryA"),
    "B": ("BCalc", "CategoryB"),
    "C": ("CCalc", "CategoryC"),
    "D": ("DCalc", "CategoryD"),
    "BE": ("BECalc", "CategoryBE"),
    "CE": ("CECalc", "CategoryCE"),
    "DE": ("DECalc", "CategoryDE"),
    "Tm": ("TmCalc", "CategoryTm"),
    "Tb": ("TbCalc", "CategoryTb"),
    "M": ("MCalc", "CategoryM"),
    "A1": ("A1Calc", "CategoryA1", "Category1A"),
    "B1": ("B1Calc", "CategoryB1", "Category1B"),
    "C1": ("C1Calc", "CategoryC1", "Category1C"),
    "D1": ("D1Calc", "CategoryD1", "Category1D"),
    "C1E": ("C1ECalc", "CategoryC1E", "Category1CE"),
    "D1E": ("D1ECalc", "CategoryD1E", "Category1DE"),
}
DRIVER_INDICATION_TOKEN_FIELDS = {
    "ManualControlCalc": ("indicationManual", ("с ручным упр", "ручн.управ", "ручн управ")),
    "AutomaticTransmissionCalc": ("indicationAutomatic", ("автоматич. трансмисс", "автоматической трансмисс", "с автоматом")),
    "ParkingSystemCalc": ("indicationAcoustic", ("акустич. парковочная", "акустической парковочной", "парковочная система")),
    "VisionTCCalc": ("indicationGlasses", ("коррекции зрения", "очки", "линзы")),
    "HearingTCCalc": ("indicationHearingAid", ("компенсации потери слуха", "слуховой аппарат")),
}
DRIVER_RESTRICTION_TOKEN_FIELDS = {
    "TCA": ("restrictionAM", ("am",)),
    "TCB": ("restrictionBBE", ("b be", "bbe")),
    "TCC": ("restrictionCCE", ("c ce", "cce")),
}


def _truthy_driver_value(value: object) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    return text not in {"", "0", "false", "no", "нет", "не установлено", "z"}


def _driver_category_tokens(value: object) -> set[str]:
    text = str(value or "")
    raw_tokens = re.findall(r"[A-Za-zА-Яа-я0-9]+", text)
    aliases = {
        "1A": "A1",
        "1B": "B1",
        "1C": "C1",
        "1D": "D1",
        "1CE": "C1E",
        "1DE": "D1E",
        "Е": "E",
        "ВЕ": "BE",
        "СЕ": "CE",
        "ДЕ": "DE",
    }
    tokens: set[str] = set()
    for token in raw_tokens:
        normalized = aliases.get(token.upper(), token)
        normalized = {"TM": "Tm", "TB": "Tb"}.get(normalized.upper(), normalized.upper())
        if normalized in DRIVER_XLS_CATEGORY_KEYS or normalized == "E":
            tokens.add(normalized)
    if "E" in tokens:
        tokens.update({"BE", "CE", "DE"})
    return tokens


def _driver_completed_chairman(exams: list[DoctorExam]) -> DoctorExam | None:
    return next(
        (
            exam
            for exam in exams
            if str(exam.doctor_role_id or "").strip().lower() == "chairman" and bool(exam.is_completed)
        ),
        None,
    )


def _driver_categories_from_chairman(fields: dict) -> set[str] | None:
    exact_fields = {field_key for field_key in DRIVER_CATEGORY_FIELD_KEYS.values() if field_key in fields}
    if "categoryE" in fields:
        exact_fields.add("categoryE")
    if exact_fields:
        selected = {
            category
            for category, field_key in DRIVER_CATEGORY_FIELD_KEYS.items()
            if _truthy_driver_value(fields.get(field_key))
        }
        if _truthy_driver_value(fields.get("categoryE")) and not selected.intersection({"BE", "CE", "DE"}):
            selected.update({"BE", "CE", "DE"})
        return selected
    driver_categories = fields.get("driverCategories")
    if str(driver_categories or "").strip():
        return _driver_category_tokens(driver_categories)
    return None


def _driver_categories_from_context(context: dict[str, str], client: Client) -> set[str]:
    selected = {
        category
        for category in DRIVER_XLS_CATEGORY_KEYS
        if _truthy_driver_value(context.get(f"Category{category}") or context.get(f"{category}Calc"))
    }
    selected.update(_driver_category_tokens(client.admission_category))
    return selected


def _driver_categories_for_documents(client: Client, exams: list[DoctorExam]) -> set[str]:
    chairman = _driver_completed_chairman(exams)
    chairman_categories = _driver_categories_from_chairman(chairman.fields_json or {}) if chairman else None
    if chairman_categories is not None:
        return chairman_categories
    return _driver_category_tokens(client.admission_category)


def _driver_category_context_values(selected: set[str], true_value: str = "X", false_value: str = "") -> dict[str, str]:
    context: dict[str, str] = {}
    for category in DRIVER_XLS_CATEGORY_KEYS:
        value = true_value if category in selected else false_value
        for key in (
            f"Category{category}",
            f"Category{category}1",
            f"{category}Calc",
            f"Category{category}Calc",
        ):
            context[key] = value
        legacy_key = DRIVER_CATEGORY_LEGACY_ALIASES.get(category)
        if legacy_key:
            for key in (
                f"Category{legacy_key}",
                f"Category{legacy_key}1",
                f"{legacy_key}Calc",
                f"Category{legacy_key}Calc",
            ):
                context[key] = value
    return context


def _driver_text_contains(value: object, needles: tuple[str, ...]) -> bool:
    text = str(value or "").strip().lower().replace("ё", "е")
    return any(needle in text for needle in needles)


def _driver_field_or_text_flag(fields: dict, field_key: str, fallback_text: object, labels: tuple[str, ...]) -> bool:
    if field_key in fields:
        return _truthy_driver_value(fields.get(field_key))
    return _driver_text_contains(fallback_text, labels)


def _driver_flag_context_values(client: Client, exams: list[DoctorExam]) -> dict[str, str]:
    chairman = _driver_completed_chairman(exams)
    fields = (chairman.fields_json or {}) if chairman else {}
    fallback_text = client.indications or ""
    context: dict[str, str] = {}
    for token, (field_key, labels) in DRIVER_INDICATION_TOKEN_FIELDS.items():
        context[token] = "true" if _driver_field_or_text_flag(fields, field_key, fallback_text, labels) else "false"
    for token, (field_key, labels) in DRIVER_RESTRICTION_TOKEN_FIELDS.items():
        context[token] = "X" if _driver_field_or_text_flag(fields, field_key, fallback_text, labels) else ""
    context["DriveShipCalc"] = "true" if _truthy_driver_value(fields.get("categoryBoat")) else "false"
    return context


def _driver_document_context_overrides(client: Client, exams: list[DoctorExam]) -> dict[str, str]:
    selected = _driver_categories_for_documents(client, exams)
    return {
        **_driver_category_context_values(selected),
        **_driver_flag_context_values(client, exams),
    }


def _bool_text(value: bool) -> str:
    return "true" if value else "false"


def _driver_xml_context_overrides(context: dict[str, str], client: Client, exams: list[DoctorExam]) -> dict[str, str]:
    selected = _driver_categories_for_documents(client, exams)
    overrides: dict[str, str] = {}
    for category, token_names in DRIVER_XML_CATEGORY_TOKENS.items():
        value = _bool_text(category in selected)
        for token_name in token_names:
            overrides[token_name] = value

    flag_context = _driver_flag_context_values(client, exams)
    overrides.update(
        {
            token_name: flag_context[token_name]
            for token_name in DRIVER_INDICATION_TOKEN_FIELDS
        }
    )
    overrides["DriveShipCalc"] = flag_context["DriveShipCalc"]
    overrides["CategoryACalc"] = _bool_text(bool(flag_context.get("TCA")))
    overrides["CategoryBCalc"] = _bool_text(bool(flag_context.get("TCB")))
    overrides["CategoryCCalc"] = _bool_text(bool(flag_context.get("TCC")))
    return overrides


def _driver_category_marks(context: dict[str, str], client: Client, exams_by_role: dict[str, DoctorExam]) -> list[str]:
    chairman = exams_by_role.get("chairman")
    chairman_categories = _driver_categories_from_chairman(chairman.fields_json or {}) if chairman and chairman.is_completed else None
    selected = chairman_categories if chairman_categories is not None else _driver_categories_from_context(context, client)
    return ["V" if category in selected else "Z" for category in DRIVER_XLS_CATEGORY_KEYS]


def _driver_marker_style(source_book, source_sheet, row_index: int, col_index: int):
    xf = source_book.xf_list[source_sheet.cell_xf_index(row_index, col_index)]
    source_border = xf.border

    style = xlwt.XFStyle()
    font = xlwt.Font()
    font.name = "Arial Cyr"
    font.height = 320
    font.bold = False
    font.italic = False
    font.underline = xlwt.Font.UNDERLINE_NONE
    style.font = font

    alignment = xlwt.Alignment()
    alignment.horz = xlwt.Alignment.HORZ_CENTER
    alignment.vert = xlwt.Alignment.VERT_CENTER
    style.alignment = alignment

    return style


def _write_driver_marker_cells(source_book, source_sheet, target_sheet, cells: tuple[tuple[int, int], ...], marks: list[str]) -> None:
    for (row_index, col_index), mark in zip(cells, marks):
        target_sheet.write(row_index, col_index, mark, _driver_marker_style(source_book, source_sheet, row_index, col_index))


def _fill_driver_xls_sheets(
    source_book,
    target_book,
    context: dict[str, str],
    client: Client,
    encounter: Encounter | None,
    exams_by_role: dict[str, DoctorExam],
) -> None:
    driver_lines = [
        _driver_exam_line(exams_by_role.get("therapist")),
        _driver_exam_line(exams_by_role.get("ophthalmologist")),
        _driver_exam_line(exams_by_role.get("neurologist"), "не установлено"),
        _driver_exam_line(exams_by_role.get("otolaryngologist"), "не установлено"),
        _driver_auxiliary_line(context, "InstrumentalExamination"),
        _driver_auxiliary_line(context, "LaboratoryStudy"),
        _build_exam_export(exams_by_role.get("chairman")).get("doctor"),
    ]
    issue_date = encounter.encounter_date if encounter else date.today()
    front_source, front_target, _ = _sheet_pair_any(source_book, target_book, DRIVER_XLS_FRONT_SHEET_NAMES)
    if front_source and front_target:
        _write_xls_pairs(
            front_target,
            front_source,
            [
                ((15, 2), context.get("ClientCalc", "")),
                ((15, 28), context.get("ClientCalc", "")),
                ((16, 8), context.get("BirthDateCalc_DAY", "")),
                ((16, 15), context.get("BirthDateCalc_DATEMONTH", "")),
                ((16, 22), context.get("BirthDateCalc_YEAR", "")),
                ((16, 35), context.get("BirthDateCalc_DAY", "")),
                ((16, 41), context.get("BirthDateCalc_DATEMONTH", "")),
                ((16, 48), context.get("BirthDateCalc_YEAR", "")),
                ((18, 9), context.get("SubjectCalc", "")),
                ((18, 36), context.get("SubjectCalc", "")),
                ((19, 4), _xls_blank_or_dash(context.get("DistrictCalc"))),
                ((19, 31), _xls_blank_or_dash(context.get("DistrictCalc"))),
                ((20, 4), context.get("CityCalc", "")),
                ((20, 30), context.get("CityCalc", "")),
                ((21, 2), context.get("StreetCalc", "")),
                ((21, 18), context.get("HouseNumberCalc", "")),
                ((21, 30), context.get("StreetCalc", "")),
                ((21, 45), context.get("HouseNumberCalc", "")),
                ((22, 3), _xls_blank_or_dash(context.get("HouseBodyCalc"))),
                ((22, 12), context.get("ApartmentNumberCalc", "")),
                ((22, 31), _xls_blank_or_dash(context.get("HouseBodyCalc"))),
                ((22, 38), context.get("ApartmentNumberCalc", "")),
                ((23, 15), issue_date.day),
                ((23, 19), context.get("VisitDate_DATEMONTH", "")),
                ((23, 23), issue_date.year),
                ((23, 41), issue_date.day),
                ((23, 45), context.get("VisitDate_DATEMONTH", "")),
                ((23, 49), issue_date.year),
                ((28, 12), driver_lines[0]),
                ((28, 39), driver_lines[0]),
                ((30, 12), driver_lines[1]),
                ((30, 39), driver_lines[1]),
                ((35, 12), driver_lines[2]),
                ((35, 39), driver_lines[2]),
                ((37, 12), driver_lines[3]),
                ((37, 39), driver_lines[3]),
                ((39, 12), driver_lines[4]),
                ((39, 39), driver_lines[4]),
                ((41, 12), driver_lines[5]),
                ((41, 39), driver_lines[5]),
            ],
        )
        for target_coord, style_coord in [
            ((28, 12), (28, 39)),
            ((30, 12), (30, 39)),
            ((35, 12), (35, 39)),
            ((37, 12), (37, 39)),
            ((39, 12), (39, 39)),
            ((41, 12), (41, 39)),
        ]:
            _copy_xls_target_cell_style(front_target, *target_coord, *style_coord)
    back_source, back_target, _ = _sheet_pair_any(source_book, target_book, DRIVER_XLS_BACK_SHEET_NAMES)
    if back_source and back_target:
        category_marks = _driver_category_marks(context, client, exams_by_role)
        _write_driver_marker_cells(source_book, back_source, back_target, DRIVER_XLS_CATEGORY_CELLS_LEFT, category_marks)
        _write_driver_marker_cells(source_book, back_source, back_target, DRIVER_XLS_CATEGORY_CELLS_RIGHT, category_marks)
        back_cells = [
            ((36, 8), driver_lines[6]),
            ((36, 41), driver_lines[6]),
        ]
        _write_xls_pairs(back_target, back_source, back_cells)


def _fill_tractor_xls_sheets(source_book, target_book, exams_by_role: dict[str, DoctorExam]) -> None:
    tractor_lines = [
        _exam_conclusion_line(exams_by_role.get("therapist")),
        _exam_conclusion_line(exams_by_role.get("ophthalmologist")),
        _exam_conclusion_line(exams_by_role.get("neurologist")),
        _exam_conclusion_line(exams_by_role.get("otolaryngologist")),
    ]
    front_source, front_target, _ = _sheet_pair(source_book, target_book, "Тракторная Лицевая")
    if front_source and front_target:
        _write_xls_pairs(
            front_target,
            front_source,
            [
                ((29, 12), tractor_lines[0]),
                ((29, 39), tractor_lines[0]),
                ((31, 12), tractor_lines[1]),
                ((31, 39), tractor_lines[1]),
                ((35, 12), tractor_lines[2]),
                ((35, 39), tractor_lines[2]),
                ((37, 12), tractor_lines[3]),
                ((37, 39), tractor_lines[3]),
            ],
        )
    back_source, back_target, _ = _sheet_pair(source_book, target_book, "Тракторная оборотная")
    if back_source and back_target:
        signer = _first_non_empty(_build_exam_export(exams_by_role.get("chairman")).get("doctor"), _build_exam_export(exams_by_role.get("therapist")).get("doctor"))
        _write_xls_pairs(
            back_target,
            back_source,
            [
                ((36, 5), signer),
                ((36, 25), signer),
            ],
        )


def _fill_amb_opo_xls_sheet(
    source_sheet,
    target_sheet,
    context: dict[str, str],
    client: Client,
    encounter: Encounter | None,
    exams_by_role: dict[str, DoctorExam],
) -> None:
    issue_date = encounter.encounter_date if encounter else date.today()
    work_place = ", ".join(part for part in [context.get("CompanyName", ""), context.get("Post", "")] if part and part != "не указано")
    _write_xls_pairs(
        target_sheet,
        source_sheet,
        [
            ((2, 35), context.get("ReferenceNumber", "")),
            ((16, 54), _xls_excel_date(issue_date)),
            ((17, 43), context.get("ClientCalc", "")),
            ((18, 35), context.get("SexCalc", "")),
            ((18, 48), _xls_excel_date(client.birth_date)),
            ((19, 54), context.get("CityCalc", "")),
            ((20, 35), context.get("DistrictCalc", "")),
            ((20, 49), context.get("CityCalc", "")),
            ((21, 40), context.get("StreetCalc", "")),
            ((22, 35), context.get("AddressCalc", "")),
            ((22, 56), context.get("Phone", "")),
            ((24, 55), context.get("SNILS", "")),
            ((26, 48), client.document_type or "Паспорт РФ"),
            ((26, 56), context.get("DocumentSeries", "")),
            ((26, 59), context.get("DocumentNumber", "")),
            ((38, 44), work_place),
            ((72, 11), _exam_export_with_client_doctor(exams_by_role.get("therapist"), client, "therapist").get("doctor", "")),
            ((72, 42), _exam_export_with_client_doctor(exams_by_role.get("psychiatrist"), client, "psychiatrist").get("doctor", "")),
            ((94, 11), _exam_export_with_client_doctor(exams_by_role.get("neurologist"), client, "neurologist").get("doctor", "")),
            ((94, 42), _exam_export_with_client_doctor(exams_by_role.get("otolaryngologist"), client, "otolaryngologist").get("doctor", "")),
        ],
    )


def _fill_journal_344_sheet(
    source_sheet,
    target_sheet,
    context: dict[str, str],
    client: Client,
    encounter: Encounter | None,
) -> None:
    issue_date = encounter.encounter_date if encounter else date.today()
    _write_xls_pairs(
        target_sheet,
        source_sheet,
        [
            ((7, 0), 1),
            ((7, 1), _xls_excel_date(issue_date)),
            ((7, 2), context.get("BlankNumber", "") or context.get("ReferenceNumber", "")),
            ((7, 3), context.get("ClientCalc", "")),
            ((7, 4), _xls_excel_date(client.birth_date)),
            ((7, 5), context.get("Conclusion", "")),
            ((7, 6), ""),
            ((7, 7), ""),
        ],
    )


def _fill_prof_extract_doctor_rows(
    source_book,
    source_sheet,
    target_sheet,
    exams_by_role: dict[str, DoctorExam],
    encounter: Encounter | None,
    client: Client | None,
) -> None:
    pairs: list[tuple[tuple[int, int], object]] = []
    for _, _, row_index in PROF_EXTRACT_DOCTOR_ROWS:
        pairs.extend(
            [
                ((row_index, PROF_EXTRACT_SEQUENCE_COL), ""),
                ((row_index, PROF_EXTRACT_DOCTOR_COL), ""),
                ((row_index, PROF_EXTRACT_DATE_COL), ""),
                ((row_index, PROF_EXTRACT_CONCLUSION_COL), ""),
            ]
        )
    row_values = _prof_extract_doctor_row_values(exams_by_role, encounter, client)
    doctor_style_by_row = {
        row_index: _xls_shrink_to_fit_style(source_book, source_sheet, row_index, PROF_EXTRACT_DOCTOR_COL)
        for row_index in {row_index for row_index, _, _, _ in row_values}
    }
    for sequence_number, (row_index, doctor_line, completed_date, conclusion) in enumerate(row_values, start=1):
        pairs.extend(
            [
                ((row_index, PROF_EXTRACT_SEQUENCE_COL), sequence_number),
                ((row_index, PROF_EXTRACT_DATE_COL), _prof_xls_display_date(completed_date)),
                ((row_index, PROF_EXTRACT_CONCLUSION_COL), conclusion),
            ]
        )
    _write_xls_pairs(target_sheet, source_sheet, pairs)
    for row_index, doctor_line, _, _ in row_values:
        _write_xls_cell(
            target_sheet,
            source_sheet,
            row_index,
            PROF_EXTRACT_DOCTOR_COL,
            doctor_line,
            doctor_style_by_row[row_index],
        )


def _find_prof_amb_sheet_index(source_book) -> int | None:
    for index, sheet_name in enumerate(source_book.sheet_names()):
        normalized = str(sheet_name or "").strip().lower().replace("!", "").strip()
        if normalized in {"амб", "àìá"}:
            return index
    return None


def _generate_prof_amb_xls(
    template_path: Path,
    output_path: Path,
    context: dict[str, str],
    client: Client,
    encounter: Encounter | None,
    exams: list[DoctorExam],
    print_variant: str | None = None,
) -> None:
    source_book = xlrd.open_workbook(file_contents=template_path.read_bytes(), formatting_info=True)
    amb_index = _find_prof_amb_sheet_index(source_book)
    if amb_index is None:
        raise ValueError("В шаблоне не найден лист амбулаторной карты")
    source_sheet = source_book.sheet_by_index(amb_index)
    target_book = copy_xls_workbook(source_book)
    target_sheet = target_book.get_sheet(amb_index)
    target_book._Workbook__active_sheet = amb_index

    exams_by_role = _exam_map(exams)
    _fill_driver_xls_sheets(source_book, target_book, context, client, encounter, exams_by_role)

    address = context.get("AddressCalc", "")
    city = context.get("CityCalc", "")
    district = context.get("DistrictCalc", "")
    street = context.get("StreetCalc", "") or address
    oms_series, oms_number = _split_policy(context.get("PolisOMS", ""))
    passport_series, passport_number = _split_document(context.get("DocumentSeries", ""), context.get("DocumentNumber", ""))
    visit_date = encounter.encounter_date if encounter else None
    work_place = ", ".join(part for part in [context.get("CompanyName", ""), context.get("Post", "")] if part and part != "не указано")

    header_values: list[tuple[tuple[int, int], object]] = [
        ((15, 54), context.get("ReferenceNumber", "")),
        ((16, 47), _xls_excel_date(visit_date)),
        ((17, 43), context.get("ClientCalc", "")),
        ((18, 35), context.get("SexCalc", "")),
        ((18, 48), _xls_excel_date(client.birth_date)),
        ((19, 54), context.get("SubjectCalc", "")),
        ((20, 35), district),
        ((20, 50), city),
        ((21, 40), city),
        ((22, 35), street),
        ((22, 56), context.get("Phone", "")),
        ((23, 48), 2 if _is_rural_address(address, city, district) else 1),
        ((24, 35), oms_series),
        ((24, 46), oms_number),
        ((24, 55), context.get("SNILS", "")),
        ((26, 48), "Паспорт РФ" if passport_series or passport_number else ""),
        ((26, 56), passport_series),
        ((26, 59), passport_number),
        ((38, 44), work_place),
    ]
    for (row_index, col_index), value in header_values:
        _write_xls_cell(target_sheet, source_sheet, row_index, col_index, value)

    _clear_xls_cells(
        target_sheet,
        source_sheet,
        [
            (30, 1),
            (31, 14),
            (33, 1),
            (40, 1),
            (43, 1),
            (45, 18),
            (45, 26),
            (47, 18),
            (47, 26),
            (47, 40),
            (47, 54),
            (48, 44),
            (49, 18),
            (49, 26),
        ],
    )

    empty_exam_block = {
        "date": "",
        "title": "",
        "complaints": "",
        "anamnesis": "",
        "objective": "",
        "diagnosis": "",
        "doctor": "",
    }
    for block in PROF_AMB_EXAM_BLOCKS:
        _fill_exam_block(target_sheet, source_sheet, empty_exam_block, source_book=source_book, **block)
    exam_block_values = _prof_amb_exam_block_values(exams_by_role, encounter, client)
    for block in PROF_AMB_EXAM_BLOCKS[len(exam_block_values) :]:
        _clear_prof_amb_exam_block(target_sheet, source_sheet, block)
    for block, (_, exam_data) in zip(PROF_AMB_EXAM_BLOCKS, exam_block_values):
        _fill_exam_block(target_sheet, source_sheet, exam_data, source_book=source_book, **block)

    pz2_source, pz2_target, _ = _sheet_pair(source_book, target_book, "ПЗ2")
    if pz2_source and pz2_target:
        _fill_prof_extract_doctor_rows(source_book, pz2_source, pz2_target, exams_by_role, encounter, client)

    _apply_xls_auto_markers(source_book, target_book, context, client, encounter, exams_by_role)
    _apply_print_variant_to_xls_workbook(target_book, print_variant)
    target_book.save(str(output_path))


def _apply_print_variant_to_xls_workbook(target_book, print_variant: str | None) -> None:
    variant = str(print_variant or "").strip().lower()
    if not variant:
        return

    sheets_by_variant = {
        "driver_front": DRIVER_XLS_FRONT_SHEET_NAMES,
        "driver_back": DRIVER_XLS_BACK_SHEET_NAMES,
        "tractor_front": ("Тракторная Лицевая",),
        "tractor_back": ("Тракторная оборотная",),
    }
    target_sheet_names = sheets_by_variant.get(variant)
    if not target_sheet_names:
        raise ValueError(f"Неизвестный вариант печати: {print_variant}")

    worksheets = list(getattr(target_book, "_Workbook__worksheets", []) or [])
    if not worksheets:
        return

    kept_sheet = next(
        (
            sheet
            for target_sheet_name in target_sheet_names
            for sheet in worksheets
            if getattr(sheet, "name", "") == target_sheet_name
        ),
        None,
    )
    if kept_sheet is None:
        raise ValueError(f"В шаблоне не найден лист для печати: {target_sheet_names[0]}")

    target_book._Workbook__worksheets = [kept_sheet]
    target_book._Workbook__worksheet_idx_from_name = {getattr(kept_sheet, "name", target_sheet_names[0]): 0}
    target_book._Workbook__active_sheet = 0


def _generate_xls(
    template_path: Path,
    output_path: Path,
    context: dict[str, str],
    client: Client,
    encounter: Encounter | None,
    exams: list[DoctorExam],
) -> None:
    source_book = xlrd.open_workbook(file_contents=template_path.read_bytes(), formatting_info=True)
    if _find_prof_amb_sheet_index(source_book) is not None:
        _generate_prof_amb_xls(template_path, output_path, context, client, encounter, exams)
        return
    shutil.copy2(template_path, output_path)


def _generate_runtime_xls(
    template_path: Path,
    output_path: Path,
    context: dict[str, str],
    client: Client,
    encounter: Encounter | None,
    runtime_values: dict[str, object],
    print_variant: str | None = None,
) -> None:
    source_book = xlrd.open_workbook(file_contents=template_path.read_bytes(), formatting_info=True)
    exams = list(runtime_values.get("exams", []))
    if _find_prof_amb_sheet_index(source_book) is not None:
        _generate_prof_amb_xls(template_path, output_path, context, client, encounter, exams, print_variant=print_variant)
        return

    target_book = copy_xls_workbook(source_book)
    exams_by_role = _exam_map(exams)

    contract_source, contract_target, _ = _sheet_pair(source_book, target_book, "Договор !")
    if contract_source and contract_target:
        _fill_contract_xls_sheet(contract_source, contract_target, context, client, encounter, runtime_values)

    source_sheet, target_sheet, _ = _sheet_pair(source_book, target_book, "086")
    if source_sheet and target_sheet:
        _fill_086_xls_sheet(source_sheet, target_sheet, context, client, encounter, exams_by_role)

    source_sheet, target_sheet, _ = _sheet_pair(source_book, target_book, "ЭЭГ")
    if source_sheet and target_sheet:
        _fill_eeg_xls_sheet(source_sheet, target_sheet, context, client, encounter, exams)

    source_sheet, target_sheet, _ = _sheet_pair(source_book, target_book, "ЧОД")
    if source_sheet and target_sheet:
        _fill_chod_xls_sheet(source_sheet, target_sheet, context, encounter)

    _fill_driver_xls_sheets(source_book, target_book, context, client, encounter, exams_by_role)
    _fill_tractor_xls_sheets(source_book, target_book, exams_by_role)

    source_sheet, target_sheet, _ = _sheet_pair(source_book, target_book, "АмбОПО !")
    if source_sheet and target_sheet:
        _fill_amb_opo_xls_sheet(source_sheet, target_sheet, context, client, encounter, exams_by_role)

    source_sheet, target_sheet, _ = _sheet_pair(source_book, target_book, "Журн344")
    if source_sheet and target_sheet:
        _fill_journal_344_sheet(source_sheet, target_sheet, context, client, encounter)

    _apply_xls_auto_markers(source_book, target_book, context, client, encounter, exams_by_role)
    _apply_print_variant_to_xls_workbook(target_book, print_variant)
    target_book.save(str(output_path))


def _first_field_value(fields: dict, *keys: str) -> str:
    lowered = {str(key).lower(): value for key, value in fields.items()}
    for key in keys:
        value = fields.get(key)
        if value in (None, ""):
            value = lowered.get(key.lower())
        if value not in (None, ""):
            return str(value).strip()
    return ""


def _sport_context_overrides(exams: list[DoctorExam]) -> dict[str, str]:
    empty_overrides = {
        "SportDiagnosis": "",
        "SportMedicalRequirements": "",
        "SportContraindications": "",
        "SportEkg": "",
        "SportEkgConclusion": "",
        "SportFluorography": "",
        "SportConclusionText": "",
        "SportConclusion": "",
        "ChairmanDoctor": "",
        "SportDoctor": "",
    }
    chairman = _exam_map(exams).get("chairman")
    if chairman is None:
        return empty_overrides

    fields = chairman.fields_json or {}
    diagnosis = _first_field_value(fields, "diagnosis", "diagnosisShort", "diagnosisText", "diagnoz")
    conclusion = _first_field_value(fields, "conclusion", "result")
    conclusion_text = _first_field_value(fields, "conclusionText", "sportConclusionText", "issuedConclusion")
    ekg = _first_field_value(fields, "ekg", "EKG", "ecg")
    ekg_conclusion = _first_field_value(fields, "ekgConclusion", "EKGConclusion", "ecgConclusion")
    medical_requirements = _first_field_value(fields, "medicalRequirements", "requirements")
    fluorography = _first_field_value(fields, "fluorography", "fluoro")
    chairman_doctor = str(chairman.doctor_name or "").strip()

    contraindications = ""
    if conclusion:
        contraindications = "выявлены" if conclusion.lower().startswith("не") else "не выявлены"

    return {
        **empty_overrides,
        "SportDiagnosis": diagnosis,
        "SportMedicalRequirements": medical_requirements,
        "SportContraindications": contraindications,
        "SportEkg": ekg,
        "SportEkgConclusion": ekg_conclusion,
        "SportFluorography": fluorography,
        "SportConclusionText": conclusion_text,
        "SportConclusion": _first_non_empty(conclusion_text, conclusion),
        "ChairmanDoctor": chairman_doctor,
        "SportDoctor": chairman_doctor,
    }


def _get_journal_info(template: DocumentTemplate) -> tuple[str, str] | None:
    name = f"{template.name} {template.file_name}".lower()
    if "вод" in name or "driver" in name:
        return ("journal_344", "Журнал 344 водительских заключений")
    if "оруж" in name or "002" in name:
        return ("journal_441", "Журнал 441 оружейных заключений")
    if "лмк" in name:
        return ("lmk", "Журнал ЛМК")
    if "086" in name:
        return ("086", "Журнал справок 086у")
    return None


def _medical_record_context_overrides(medical_record: MedicalRecord | None) -> dict[str, str]:
    overrides: dict[str, str] = {
        "HealthGroup": "",
        "BloodType": "",
        "qdfMain.BloodType": "",
        "gdfMain.BloodType": "",
    }
    if medical_record is None:
        return overrides

    if medical_record.marital_status:
        overrides["MaritalStatus"] = medical_record.marital_status
    if medical_record.work_place:
        overrides["CompanyName"] = medical_record.work_place
        overrides["WorkPlace"] = medical_record.work_place
        overrides["qdfMain.WorkPlace"] = medical_record.work_place
    if medical_record.position:
        overrides["Post"] = medical_record.position
        overrides["PositionApplied"] = medical_record.position
        overrides["qdfMain.Post"] = medical_record.position
    if medical_record.health_group:
        overrides["HealthGroup"] = medical_record.health_group
        overrides["BloodType"] = medical_record.health_group
        overrides["qdfMain.BloodType"] = medical_record.health_group
        overrides["gdfMain.BloodType"] = medical_record.health_group
    return overrides


def _apply_context_overrides(context: dict[str, str], overrides: dict[str, object] | None) -> None:
    context.update(
        {
            key: str(value).strip()
            for key, value in (overrides or {}).items()
            if value is not None
        }
    )


def _load_encounter_document_values(db: Session, client: Client, encounter: Encounter | None) -> dict[str, object]:
    if encounter is None:
        fallback_services = client.legacy_payload_json.get("services", []) if isinstance(client.legacy_payload_json, dict) else []
        service_names = [str(item).strip() for item in fallback_services if str(item).strip()]
        service_rows = [
            {
                "ordinal": str(index),
                "service": name,
                "quantity": "1",
                "date": date.today().strftime("%d.%m.%y"),
                "unit_price": "",
                "line_total": "",
            }
            for index, name in enumerate(service_names, start=1)
        ]
        medical_record = db.execute(
            select(MedicalRecord)
            .where(MedicalRecord.client_id == client.id, MedicalRecord.deleted_at.is_(None))
            .order_by(MedicalRecord.updated_at.desc(), MedicalRecord.id.desc())
        ).scalars().first()
        context_overrides = _medical_record_context_overrides(medical_record)
        return {
            "service_names": service_names,
            "service_rows": service_rows,
            "doctor_name": "",
            "diagnosis": "",
            "mkb10": "",
            "exams": [],
            "context_overrides": context_overrides,
        }

    service_items = (
        db.execute(
            select(EncounterService, Service.name)
            .join(Service, EncounterService.service_id == Service.id)
            .where(EncounterService.encounter_id == encounter.id)
            .order_by(EncounterService.id.asc())
        )
        .all()
    )
    service_names = [name for _, name in service_items]
    service_rows = [
        {
            "ordinal": str(index),
            "service": name,
            "quantity": str(item.quantity or 1),
            "date": encounter.encounter_date.strftime("%d.%m.%y"),
            "unit_price": str(item.unit_price or ""),
            "line_total": str(item.line_total or ""),
        }
        for index, (item, name) in enumerate(service_items, start=1)
    ]
    if not service_rows:
        fallback_services = client.legacy_payload_json.get("services", []) if isinstance(client.legacy_payload_json, dict) else []
        service_names = [str(item).strip() for item in fallback_services if str(item).strip()]
        service_rows = [
            {
                "ordinal": str(index),
                "service": name,
                "quantity": "1",
                "date": encounter.encounter_date.strftime("%d.%m.%y"),
                "unit_price": "",
                "line_total": "",
            }
            for index, name in enumerate(service_names, start=1)
        ]

    exams = (
        db.execute(
            select(DoctorExam)
            .where(DoctorExam.encounter_id == encounter.id, DoctorExam.deleted_at.is_(None))
            .order_by(DoctorExam.updated_at.desc(), DoctorExam.id.desc())
        )
        .scalars()
        .all()
    )
    doctor_names: list[str] = []
    diagnosis = ""
    mkb10 = ""
    medical_record = db.execute(
        select(MedicalRecord)
        .where(MedicalRecord.client_id == client.id, MedicalRecord.deleted_at.is_(None))
        .order_by(MedicalRecord.updated_at.desc(), MedicalRecord.id.desc())
    ).scalars().first()
    context_overrides = _medical_record_context_overrides(medical_record)
    context_overrides.update(
        {
            "Weight": "",
            "Height": "",
            "HairColor": "",
            "EyeColor": "",
            "DistinguishingMark": "",
        }
    )
    for exam in exams:
        if exam.doctor_name and exam.doctor_name not in doctor_names:
            doctor_names.append(exam.doctor_name)
        fields = exam.fields_json or {}
        diagnosis = diagnosis or _first_field_value(
            fields,
            "diagnosis",
            "diagnosisShort",
            "diagnosisText",
            "diagnose",
            "diagnoz",
            "conclusion",
        )
        mkb10 = mkb10 or _first_field_value(fields, "mkb10", "mkb", "icd10")
        context_overrides["Weight"] = context_overrides["Weight"] or _first_field_value(fields, "weight", "Weight")
        context_overrides["Height"] = context_overrides["Height"] or _first_field_value(fields, "height", "Height")
        context_overrides["HairColor"] = context_overrides["HairColor"] or _first_field_value(
            fields, "hairColor", "hair", "hair_color"
        )
        context_overrides["EyeColor"] = context_overrides["EyeColor"] or _first_field_value(
            fields, "eyeColor", "eyesColor", "eye_color"
        )
        context_overrides["DistinguishingMark"] = context_overrides["DistinguishingMark"] or _first_field_value(
            fields, "distinguishingMark", "distinguishingMarks", "specialMarks", "special_mark"
        )
    context_overrides.update(
        {
            key: value
            for key, value in _driver_document_context_overrides(client, exams).items()
            if value not in (None, "")
        }
    )
    context_overrides.update(
        {
            key: value
            for key, value in _sport_context_overrides(exams).items()
            if value not in (None, "")
        }
    )

    return {
        "service_names": service_names,
        "service_rows": service_rows,
        "doctor_name": ", ".join(doctor_names),
        "diagnosis": diagnosis,
        "mkb10": mkb10,
        "exams": exams,
        "context_overrides": context_overrides,
    }


def _append_blank_entry_to_medical_record_legacy(
    db: Session,
    *,
    client: Client,
    encounter: Encounter,
    blank_number: str,
) -> None:
    medical_record = db.execute(
        select(MedicalRecord).where(MedicalRecord.client_id == client.id, MedicalRecord.deleted_at.is_(None))
    ).scalar_one_or_none()
    if medical_record is None:
        medical_record = MedicalRecord(
            client_id=client.id,
            center_id=encounter.center_id,
            card_number=client.card_number,
            opened_at=encounter.encounter_date,
            oms_policy=client.oms_policy,
            work_place=client.work_place,
            position=client.profession,
            mkb10=client.mkb10,
            notes=client.notes,
        )
        db.add(medical_record)
        db.flush()

    db.add(
        MedicalRecordEntry(
            medical_record_id=medical_record.id,
            encounter_id=encounter.id,
            entry_date=encounter.encounter_date,
            doctor_role_id="document",
            doctor_name="document",
            conclusion=f"Выдан номерной бланк медицинского заключения №{blank_number}",
        )
    )


def _append_blank_entry_to_medical_record(
    db: Session,
    *,
    client: Client,
    encounter: Encounter,
    blank_number: str,
) -> None:
    conclusion = f"Выдан номерной бланк медицинского заключения №{blank_number}"
    medical_record = db.execute(
        select(MedicalRecord).where(MedicalRecord.client_id == client.id, MedicalRecord.deleted_at.is_(None))
    ).scalar_one_or_none()
    if medical_record is None:
        medical_record = MedicalRecord(
            client_id=client.id,
            center_id=encounter.center_id,
            card_number=client.card_number,
            opened_at=encounter.encounter_date,
            oms_policy=client.oms_policy,
            work_place=client.work_place,
            position=client.profession,
            mkb10=client.mkb10,
            notes=client.notes,
        )
        db.add(medical_record)
        db.flush()

    existing_entry = db.execute(
        select(MedicalRecordEntry).where(
            MedicalRecordEntry.medical_record_id == medical_record.id,
            MedicalRecordEntry.encounter_id == encounter.id,
            MedicalRecordEntry.doctor_role_id == "document",
            MedicalRecordEntry.conclusion == conclusion,
        )
    ).scalar_one_or_none()
    if existing_entry is not None:
        return

    db.add(
        MedicalRecordEntry(
            medical_record_id=medical_record.id,
            encounter_id=encounter.id,
            entry_date=encounter.encounter_date,
            doctor_role_id="document",
            doctor_name="document",
            conclusion=conclusion,
        )
    )


def generate_document(
    db: Session,
    *,
    template_id: int | None,
    template_code: str | None,
    client_id: int,
    encounter_id: int | None,
    blank_form_id: int | None = None,
    print_variant: str | None = None,
) -> DocumentGenerateResponse:
    print_variant_value = str(print_variant or "").strip().lower()
    side_print_variants = {"driver_front", "driver_back", "tractor_front", "tractor_back"}
    is_side_print = print_variant_value in side_print_variants
    template = None
    if template_id is not None:
        template = db.get(DocumentTemplate, template_id)
    elif template_code is not None:
        template = db.execute(select(DocumentTemplate).where(DocumentTemplate.code == template_code)).scalar_one_or_none()

    if template is None or not template.file_path:
        raise ValueError("Шаблон не найден")

    client = db.get(Client, client_id)
    if client is None or client.deleted_at is not None:
        raise ValueError("Клиент не найден")

    encounter = None
    if encounter_id is not None:
        encounter = db.get(Encounter, encounter_id)
        if encounter is None or encounter.deleted_at is not None:
            raise ValueError("Обращение не найдено")

    template_path = Path(template.file_path)
    output_dir = Path(settings.generated_documents_dir)
    if _is_contract_template(template):
        output_dir = output_dir / "contracts"
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file_name = f"{template_path.stem}_{client.id}_{timestamp}{template_path.suffix}"
    output_path = output_dir / output_file_name

    runtime_values = _load_encounter_document_values(db, client, encounter)
    required_blank_type = None if is_side_print else resolve_required_blank_type(template)
    blank_form = None

    try:
        if required_blank_type:
            if encounter is None or encounter.center_id is None:
                raise ValueError(
                    "Для документа с номерным бланком требуется encounter_id и center_id. "
                    "Сначала оформите обращение в нужном медцентре."
                )

            blank_form = reuse_blank_for_existing_document(
                db,
                blank_type=required_blank_type,
                client_id=client.id,
                encounter_id=encounter.id,
                template_id=template.id,
            )
            if blank_form is None:
                if blank_form_id is not None:
                    blank_form = issue_specific_blank(
                        db,
                        form_id=blank_form_id,
                        blank_type=required_blank_type,
                        client_id=client.id,
                        center_id=encounter.center_id,
                        encounter_id=encounter.id,
                        user_id=1,
                    )
                else:
                    blank_form = issue_next_blank(
                        db,
                        blank_type=required_blank_type,
                        client_id=client.id,
                        center_id=encounter.center_id,
                        encounter_id=encounter.id,
                        user_id=1,
                    )

        elif blank_form_id is not None and not is_side_print:
            if encounter is None or encounter.center_id is None:
                raise ValueError(
                    "Р”Р»СЏ РїРµС‡Р°С‚Рё РЅР° РЅРѕРјРµСЂРЅРѕРј Р±Р»Р°РЅРєРµ С‚СЂРµР±СѓРµС‚СЃСЏ encounter_id Рё center_id. "
                    "РЎРЅР°С‡Р°Р»Р° РѕС„РѕСЂРјРёС‚Рµ РѕР±СЂР°С‰РµРЅРёРµ РІ РЅСѓР¶РЅРѕРј РјРµРґС†РµРЅС‚СЂРµ."
                )
            candidate_form = db.get(BlankForm, blank_form_id)
            if candidate_form is None:
                raise ValueError("Р‘Р»Р°РЅРє РЅРµ РЅР°Р№РґРµРЅ")
            blank_type = template.blank_type or candidate_form.blank_type or BLANK_TYPE_DRIVER_MEDICAL_CERTIFICATE
            if candidate_form.status == BLANK_STATUS_FREE:
                blank_form = issue_specific_blank(
                    db,
                    form_id=blank_form_id,
                    blank_type=blank_type,
                    client_id=client.id,
                    center_id=encounter.center_id,
                    encounter_id=encounter.id,
                    user_id=1,
                )
            elif (
                candidate_form.status == BLANK_STATUS_ISSUED
                and candidate_form.client_id == client.id
                and candidate_form.encounter_id == encounter.id
            ):
                blank_form = candidate_form
            else:
                raise ValueError("Р’С‹Р±СЂР°РЅРЅС‹Р№ Р±Р»Р°РЅРє СѓР¶Рµ РЅРµРґРѕСЃС‚СѓРїРµРЅ РґР»СЏ СЌС‚РѕР№ РїРµС‡Р°С‚Рё")

        if is_side_print and blank_form_id is not None:
            if encounter is None or encounter.center_id is None:
                raise ValueError(
                    "Для печати на номерном бланке требуется encounter_id и center_id. "
                    "Сначала оформите обращение в нужном медцентре."
                )
            candidate_form = db.get(BlankForm, blank_form_id)
            if candidate_form is None:
                raise ValueError("Бланк не найден")
            if candidate_form.status == BLANK_STATUS_FREE:
                blank_form = issue_specific_blank(
                    db,
                    form_id=blank_form_id,
                    blank_type=template.blank_type or BLANK_TYPE_DRIVER_MEDICAL_CERTIFICATE,
                    client_id=client.id,
                    center_id=encounter.center_id,
                    encounter_id=encounter.id,
                    user_id=1,
                )
            elif (
                candidate_form.status == BLANK_STATUS_ISSUED
                and candidate_form.client_id == client.id
                and candidate_form.encounter_id == encounter.id
            ):
                blank_form = candidate_form
            else:
                raise ValueError("Выбранный бланк уже недоступен для этой печати")

        context = build_document_context(
            client,
            encounter,
            service_names=runtime_values["service_names"],
            doctor_name=runtime_values["doctor_name"],
            diagnosis=runtime_values["diagnosis"],
            mkb10=runtime_values["mkb10"],
        )
        _apply_context_overrides(context, runtime_values.get("context_overrides"))
        document_exams = list(runtime_values.get("exams", []))
        context.update(_driver_document_context_overrides(client, document_exams))
        context.update(
            {
                key: str(value or "").strip()
                for key, value in _sport_context_overrides(document_exams).items()
            }
        )
        if blank_form is not None:
            context["BlankNumber"] = blank_form.full_number
            context["BlankSeries"] = blank_form.series or ""
            context["BlankFullNumber"] = blank_form.full_number
            context["DocumentNumber"] = blank_form.full_number
        if is_side_print:
            context["ReferenceNumber"] = ""
            context["SeriesNumberCalc"] = ""
            context["BlankNumber"] = ""
            context["BlankSeries"] = ""
            context["BlankFullNumber"] = ""

        if template.template_type == "docx":
            _generate_docx(
                template_path,
                output_path,
                context,
                runtime_values["service_rows"],
                cleanup_xml=_is_contract_template(template),
            )
        elif template.template_type == "xml":
            xml_context = context.copy()
            xml_context.update(_driver_xml_context_overrides(xml_context, client, document_exams))
            _generate_xml(template_path, output_path, xml_context)
        elif template.template_type == "xls":
            _generate_runtime_xls(
                template_path,
                output_path,
                context,
                client,
                encounter,
                runtime_values,
                print_variant=print_variant,
            )
        else:
            shutil.copy2(template_path, output_path)

        document_number = blank_form.full_number if blank_form is not None else client.reference_number
        document_series = blank_form.series if blank_form is not None else client.document_series

        generated_document = GeneratedDocument(
            encounter_id=encounter.id if encounter else None,
            client_id=client.id,
            template_id=template.id,
            document_number=document_number,
            series=document_series,
            file_name=output_file_name,
            file_path=str(output_path.resolve()),
            generated_by_user_id=1,
            blank_form_id=blank_form.id if blank_form is not None else None,
            blank_number_snapshot=blank_form.full_number if blank_form is not None else None,
        )
        db.add(generated_document)
        db.flush()

        if blank_form is not None and blank_form.generated_document_id is None:
            blank_form.generated_document_id = generated_document.id
            db.flush()

        journal_info = _get_journal_info(template)
        if journal_info is not None:
            journal_code, journal_name = journal_info
            db.add(
                DocumentJournalEntry(
                    journal_code=journal_code,
                    journal_name=journal_name,
                    generated_document_id=generated_document.id,
                    client_id=client.id,
                    encounter_id=encounter.id if encounter else None,
                    issued_at=encounter.encounter_date if encounter else None,
                    series=generated_document.series,
                    number=generated_document.document_number,
                    result_text=context.get("Diagnosis") or context.get("Conclusion") or "",
                    created_by_user_id=1,
                )
            )

        if blank_form is not None and encounter is not None:
            _append_blank_entry_to_medical_record(
                db,
                client=client,
                encounter=encounter,
                blank_number=blank_form.full_number,
            )

        write_audit_log(
            db,
            entity_type="document_template",
            entity_id=template.id,
            action="generate",
            user_id=1,
            center_id=encounter.center_id if encounter else None,
            payload_json={
                "client_id": client.id,
                "encounter_id": encounter.id if encounter else None,
                "blank_form_id": blank_form.id if blank_form is not None else None,
                "blank_number": blank_form.full_number if blank_form is not None else None,
            },
        )

        return DocumentGenerateResponse(
            template_name=template.name,
            template_type=template.template_type,
            output_file_name=output_file_name,
            output_file_path=str(output_path.resolve()),
            generated_document_id=generated_document.id,
            blank_form_id=blank_form.id if blank_form is not None else None,
            blank_number=blank_form.full_number if blank_form is not None else None,
            generated_fields=context,
        )
    except Exception:
        if output_path.exists():
            output_path.unlink(missing_ok=True)
        raise
