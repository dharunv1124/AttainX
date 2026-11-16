import io
import re
from typing import Any
from xml.sax.saxutils import escape

from fastapi import HTTPException, status
from openpyxl import Workbook
from openpyxl.drawing.image import Image as ExcelImage
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A3, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy.orm import Session

from app.db.models import Section, Subject
from app.domain.course_obe_attainment import (
    calculate_course_overall_co_attainment,
    calculate_course_po_attainment,
    calculate_course_po_attainment_overall,
)
from app.repositories.course_obe_attainment_repository import CourseCOAttainmentRepository
from app.repositories.course_obe_repository import CourseCOPOMappingRepository
from app.services.course_obe_context import get_course_obe_subject_for_section
from app.schemas.course_obe import CO_ROW_COUNT, MAPPING_COLUMN_COUNT
from app.services.report_branding import (
    APPLICATION_NAME,
    DARK_GREY,
    LIGHT_BLUE,
    LIGHT_GREY,
    LOGO_PATH,
    MID_GREY,
    NAVY,
    PALE_BLUE,
    BLUE,
    NumberedCanvas,
    add_excel_logo,
    draw_college_page_header,
    set_excel_monochrome_theme,
)

COURSE_OUTCOMES = [f"CO{index}" for index in range(1, CO_ROW_COUNT + 1)]
VISIBLE_PO_INDEXES = [*range(0, 11), 12, 13]
PO_COLUMNS = [
    *(f"PO{index}" for index in range(1, 12)),
    "PSO1",
    "PSO2",
]
OVERALL_COLUMNS = [
    ("A (INT1)", "input", "a"),
    ("B (INT2)", "input", "b"),
    ("C (MODEL)", "input", "c"),
    ("Average", "result", "average"),
    ("Attainment", "result", "attainment"),
    ("University", "input", "university"),
    ("Attainment", "result", "university_attainment"),
    ("D (20%)", "result", "d"),
    ("E (80%)", "result", "e"),
    ("F", "result", "f"),
    ("90% of F", "result", "ninety_percent_f"),
    ("G", "input", "g"),
    ("10% of G", "result", "ten_percent_g"),
    ("Overall CO", "result", "overall_co"),
]


def _empty_inputs() -> list[dict[str, None]]:
    return [
        {"a": None, "b": None, "c": None, "university": None, "g": None}
        for _ in range(CO_ROW_COUNT)
    ]


def _filename_token(value: str) -> str:
    cleaned = re.sub(r"[^\w\s-]", "", value).strip()
    return re.sub(r"[-\s]+", "_", cleaned) or "Report"


class CourseOBEReportService:
    def __init__(self, db: Session):
        self.db = db

    def get_report_data(self, subject_id: int, section_id: int) -> dict[str, Any]:
        subject = get_course_obe_subject_for_section(self.db, subject_id, section_id)
        if subject.department is None or subject.year is None or subject.semester is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Course OBE report requires a subject with department, year, and semester scope.",
            )

        section = self.db.query(Section).filter(Section.id == section_id).one()
        mapping_record = CourseCOPOMappingRepository(self.db).get_for_context(subject_id, section_id)
        mappings = mapping_record.mapping_data if mapping_record else [
            [None for _ in range(MAPPING_COLUMN_COUNT)] for _ in range(CO_ROW_COUNT)
        ]
        attainment_record = CourseCOAttainmentRepository(self.db).get_for_context(subject_id, section_id)
        inputs = attainment_record.input_data if attainment_record else _empty_inputs()
        results = calculate_course_overall_co_attainment(inputs)
        po_values = calculate_course_po_attainment(mappings, results)
        po_overall_values = calculate_course_po_attainment_overall(po_values)

        return {
            "metadata": {
                "department": subject.department.name,
                "department_code": subject.department.code,
                "year": subject.year.name,
                "semester": subject.semester.name,
                "semester_number": subject.semester.semester_number,
                "section": section.name,
                "subject": subject.name,
            },
            "mappings": mappings,
            "inputs": inputs,
            "results": results,
            "po_values": po_values,
            "po_overall_values": po_overall_values,
            "filename": "{}_Sem{}_{}_{}_Course_OBE_Analysis".format(
                _filename_token(subject.department.code),
                subject.semester.semester_number,
                _filename_token(section.name),
                _filename_token(subject.name),
            ),
        }

    @staticmethod
    def _overall_rows(data: dict[str, Any]) -> list[list[Any]]:
        rows = []
        for row_index, outcome in enumerate(COURSE_OUTCOMES):
            row: list[Any] = [outcome]
            for _, value_type, key in OVERALL_COLUMNS:
                value = data["inputs"][row_index][key] if value_type == "input" else data["results"][row_index][key]
                row.append(value if value is not None or value_type == "input" else "—")
            rows.append(row)
        return rows

    @staticmethod
    def _mapping_rows(data: dict[str, Any]) -> list[list[Any]]:
        return [
            [outcome, *["-" if data["mappings"][row_index][visible_index] is None else data["mappings"][row_index][visible_index] for visible_index in VISIBLE_PO_INDEXES]]
            for row_index, outcome in enumerate(COURSE_OUTCOMES)
        ]

    @staticmethod
    def _po_rows(data: dict[str, Any]) -> list[list[Any]]:
        rows = []
        for row_index, outcome in enumerate(COURSE_OUTCOMES):
            row: list[Any] = [outcome]
            for visible_index in VISIBLE_PO_INDEXES:
                mapping = data["mappings"][row_index][visible_index]
                if mapping is None:
                    row.append("-")
                else:
                    row.append(data["po_values"][row_index][visible_index])
            rows.append(row)
        rows.append(["Overall", *[data["po_overall_values"][visible_index] for visible_index in VISIBLE_PO_INDEXES]])
        return rows

    @staticmethod
    def _display_value(value: Any, column_index: int, *, table: str) -> str:
        if value is None:
            return "" if table in ("input", "po_overall") else "—"
        if table == "overall" and column_index in (5, 7):
            return str(value)
        if isinstance(value, (int, float)):
            if table in ("po", "po_overall") or (table == "overall" and column_index not in (0, 1, 2, 5, 12)):
                return f"{value:.2f}"
        return str(value)

    def generate_excel_report(self, subject_id: int, section_id: int) -> tuple[io.BytesIO, str]:
        data = self.get_report_data(subject_id, section_id)
        workbook = Workbook()
        set_excel_monochrome_theme(workbook)
        worksheet = workbook.active
        worksheet.title = "Course OBE Analysis"
        worksheet.sheet_view.showGridLines = False

        title_font = Font(name="Aptos Display", size=14, bold=True, color="000000")
        section_font = Font(name="Aptos", size=11, bold=True, color="000000")
        header_font = Font(name="Aptos", size=9, bold=True, color="000000")
        body_font = Font(name="Aptos", size=9, color="000000")
        metadata_font = Font(name="Aptos", size=9, color="000000")
        metadata_label_font = Font(name="Aptos", size=9, bold=True, color="000000")
        overall_po_font = Font(name="Aptos", size=9, bold=True, color="000000")
        dark_fill = PatternFill("solid", fgColor="FFFFFF")
        header_fill = PatternFill("solid", fgColor="FFFFFF")
        metadata_fill = PatternFill("solid", fgColor="FFFFFF")
        alternate_fill = PatternFill("solid", fgColor="FFFFFF")
        thin_side = Side(style="thin", color="000000")
        border = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)
        centered = Alignment(horizontal="center", vertical="center", wrap_text=True)

        def add_section_title(row: int, title: str) -> None:
            worksheet.merge_cells(start_row=row, start_column=1, end_row=row, end_column=14)
            for cell in worksheet[row][:14]:
                cell.fill = dark_fill
                cell.border = border
            cell = worksheet.cell(row=row, column=1, value=title)
            cell.font = section_font
            cell.alignment = Alignment(horizontal="left", vertical="center")
            worksheet.row_dimensions[row].height = 22

        def add_table(row: int, headers: list[str], values: list[list[Any]], kind: str) -> None:
            for column_index, header in enumerate(headers, start=1):
                cell = worksheet.cell(row=row, column=column_index, value=header)
                cell.font = header_font
                cell.fill = header_fill
                cell.border = border
                cell.alignment = centered
                worksheet.column_dimensions[get_column_letter(column_index)].width = max(
                    12,
                    min(21, len(header) + 3),
                )
            worksheet.row_dimensions[row].height = 30
            for row_offset, values_row in enumerate(values, start=1):
                for column_index, value in enumerate(values_row, start=1):
                    cell = worksheet.cell(row=row + row_offset, column=column_index, value=value)
                    cell.font = body_font
                    cell.border = border
                    cell.alignment = centered
                    if kind == "po" and values_row[0] == "Overall":
                        cell.font = overall_po_font
                        cell.fill = metadata_fill
                    elif row_offset % 2 == 0:
                        cell.fill = alternate_fill
                    if isinstance(value, (int, float)) and kind == "po":
                        cell.number_format = "0.00"
                    elif isinstance(value, (int, float)) and kind == "overall":
                        if column_index in (5, 9, 10, 11, 12, 14, 15):
                            cell.number_format = "0.00"
                        elif column_index in (6, 8):
                            cell.number_format = "0"
                        else:
                            cell.number_format = "0.##"

        worksheet.merge_cells(start_row=1, start_column=1, end_row=1, end_column=14)
        worksheet.row_dimensions[1].height = 8
        worksheet.merge_cells(start_row=2, start_column=1, end_row=2, end_column=14)
        title_cell = worksheet.cell(row=2, column=1, value="COURSE OBE ANALYSIS REPORT")
        title_cell.font = title_font
        title_cell.fill = dark_fill
        title_cell.alignment = centered
        for cell in worksheet[2][:14]:
            cell.fill = dark_fill
        worksheet.row_dimensions[2].height = 28

        for row, (label, key) in enumerate((
            ("Department", "department"),
            ("Academic Year", "year"),
            ("Semester", "semester"),
            ("Section", "section"),
            ("Subject", "subject"),
        ), start=4):
            label_cell = worksheet.cell(row=row, column=1, value=label)
            label_cell.font = metadata_label_font
            label_cell.fill = metadata_fill
            label_cell.border = border
            worksheet.merge_cells(start_row=row, start_column=2, end_row=row, end_column=14)
            value_cell = worksheet.cell(row=row, column=2, value=data["metadata"][key])
            value_cell.font = metadata_font
            value_cell.fill = metadata_fill
            value_cell.border = border
            value_cell.alignment = Alignment(vertical="center")
            worksheet.row_dimensions[row].height = 20

        add_section_title(10, "1. CO-PO Mapping")
        add_table(11, ["CO", *PO_COLUMNS], self._mapping_rows(data), "mapping")
        add_section_title(18, "2. Computation of Overall CO Attainment in this Course")
        add_table(19, ["CO", *[column[0] for column in OVERALL_COLUMNS]], self._overall_rows(data), "overall")
        add_section_title(26, "3. PO Attainment")
        add_table(27, ["CO", *PO_COLUMNS], self._po_rows(data), "po")

        worksheet.freeze_panes = None
        worksheet.sheet_properties.pageSetUpPr.fitToPage = True
        worksheet.page_setup.orientation = "landscape"
        worksheet.page_setup.paperSize = worksheet.PAPERSIZE_A3
        worksheet.page_setup.fitToWidth = 1
        worksheet.page_setup.fitToHeight = 0
        worksheet.page_margins.left = 0.25
        worksheet.page_margins.right = 0.25
        worksheet.page_margins.top = 0.4
        worksheet.page_margins.bottom = 0.4
        worksheet.print_title_rows = None
        worksheet.print_area = None
        stream = io.BytesIO()
        workbook.save(stream)
        stream.seek(0)
        return stream, f"{data['filename']}.xlsx"

    def generate_pdf_report(self, subject_id: int, section_id: int) -> tuple[io.BytesIO, str]:
        data = self.get_report_data(subject_id, section_id)
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=landscape(A3),
            leftMargin=32,
            rightMargin=32,
            topMargin=86,
            bottomMargin=34,
            title="Course OBE Analysis Report",
            pageCompression=0,
        )
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            "CourseOBEReportTitle",
            parent=styles["Title"],
            fontName="Helvetica-Bold",
            fontSize=15,
            leading=18,
            textColor=colors.black,
            alignment=1,
            spaceAfter=8,
        )
        section_style = ParagraphStyle(
            "CourseOBESection",
            parent=styles["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=14,
            textColor=colors.black,
            spaceBefore=4,
            spaceAfter=6,
        )
        label_style = ParagraphStyle(
            "CourseOBEMetaLabel",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=9,
            leading=12,
            textColor=colors.black,
        )
        value_style = ParagraphStyle(
            "CourseOBEMetaValue",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=9,
            leading=12,
            textColor=colors.black,
        )
        header_style = ParagraphStyle(
            "CourseOBETableHeader",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=10,
            alignment=1,
            textColor=colors.black,
        )
        cell_style = ParagraphStyle(
            "CourseOBETableCell",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=8,
            leading=10,
            alignment=1,
            textColor=colors.black,
        )
        first_cell_style = ParagraphStyle(
            "CourseOBEFirstCell",
            parent=cell_style,
            fontName="Helvetica-Bold",
        )
        overall_cell_style = ParagraphStyle(
            "CourseOBEPOOverallCell",
            parent=cell_style,
            fontName="Helvetica-Bold",
            textColor=colors.black,
        )

        mapping_headers = ["CO", *PO_COLUMNS]
        overall_headers = ["CO", *[column[0] for column in OVERALL_COLUMNS]]
        tables = [
            ("1. CO-PO Mapping", mapping_headers, self._mapping_rows(data), "mapping"),
            (
                "2. Computation of Overall CO Attainment in this Course",
                overall_headers,
                self._overall_rows(data),
                "overall",
            ),
            ("3. PO Attainment", mapping_headers, self._po_rows(data), "po"),
        ]

        story = []
        page_width = landscape(A3)[0] - doc.leftMargin - doc.rightMargin

        metadata_rows = [
            [Paragraph(f"<b>{label}</b>", label_style), Paragraph(escape(data["metadata"][key]), value_style)]
            for label, key in (
                ("Department", "department"),
                ("Academic Year", "year"),
                ("Semester", "semester"),
                ("Section", "section"),
                ("Subject", "subject"),
            )
        ]
        metadata_table = Table(metadata_rows, colWidths=[92, page_width - 92])
        metadata_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.white),
            ("BOX", (0, 0), (-1, -1), 0.8, colors.black),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.black),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.extend([
            Paragraph("COURSE OBE ANALYSIS REPORT", title_style),
            metadata_table,
            Spacer(1, 10),
        ])

        for section_title, headers, rows, kind in tables:
            story.append(Paragraph(escape(section_title), section_style))

            table_data = [[Paragraph(escape(header), header_style) for header in headers]]
            for row in rows:
                row_kind = "po_overall" if kind == "po" and row[0] == "Overall" else kind
                displayed = [
                    self._display_value(value, column_index, table=("input" if row_kind == "overall" and column_index in (1, 2, 3, 6, 12) else row_kind))
                    for column_index, value in enumerate(row)
                ]
                table_data.append([
                    Paragraph(
                        escape(value),
                        first_cell_style if column_index == 0 else overall_cell_style if row_kind == "po_overall" else cell_style,
                    )
                    for column_index, value in enumerate(displayed)
                ])
            first_width = 54
            other_width = (page_width - first_width) / (len(headers) - 1)
            report_table = Table(
                table_data,
                colWidths=[first_width, *([other_width] * (len(headers) - 1))],
                repeatRows=1,
                hAlign="LEFT",
            )
            table_styles = [
                ("BACKGROUND", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.75, colors.black),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("BACKGROUND", (0, 1), (-1, -1), colors.white),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.white]),
                ("LEFTPADDING", (0, 0), (-1, -1), 3),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
            if kind == "po":
                table_styles.append(("BACKGROUND", (0, -1), (-1, -1), colors.white))
            report_table.setStyle(TableStyle(table_styles))
            story.append(report_table)

        doc.build(
            story,
            canvasmaker=NumberedCanvas,
        )
        buffer.seek(0)
        return buffer, f"{data['filename']}.pdf"