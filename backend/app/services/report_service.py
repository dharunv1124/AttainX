"""
Phase 7 - Authoritative Excel and PDF Report Generation Service.

Strictly adheres to:
1. Authoritative Phase 3 domain engine for all calculation values.
2. Saved state from database / repository as single source of truth.
3. Clean, printable, professional Excel and PDF formats.
4. Numeric 1 / 0 attainment values only (no PASS/FAIL).
5. No unapproved analytics, BT, PO/PSO, or decorative clutter.
"""

import io
import re
from typing import Any, Dict, List, Tuple
from xml.sax.saxutils import escape
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.db.models import Exam, Section
from app.repositories.marks_repository import MarksRepository
from app.services.marks_service import MarksApiService
from app.domain.marks_service import (
    calculate_exam_co_statistics,
    process_exam_marks_and_calculate,
    CohortConsistencyError,
)
from app.domain.errors import IncompleteDataError, DomainValidationError

# Openpyxl for Excel reporting
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils import get_column_letter

# ReportLab for PDF reporting
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, A2
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from app.services.report_branding import (
    BLUE,
    DARK_GREY,
    LIGHT_BLUE,
    LIGHT_GREY,
    MID_GREY,
    NAVY,
    PALE_BLUE,
    NumberedCanvas,
    add_excel_logo,
    draw_college_page_header,
    set_excel_monochrome_theme,
)


def sanitize_filename_token(text: str) -> str:
    """Sanitizes text for safe use in file download filenames."""
    if not text:
        return "Report"
    cleaned = re.sub(r"[^\w\s-]", "", text).strip()
    return re.sub(r"[-\s]+", "_", cleaned)


class ExamReportService:
    def __init__(self, db: Session):
        self.db = db
        self.marks_service = MarksApiService(db)
        self.marks_repo = MarksRepository(db)

    def _canonical_section_filename_token(self, exam: Exam) -> str:
        """Use the standard department/year section letter when one exists; otherwise fall back to the raw section name."""
        section_name = exam.section.name.strip() if exam.section and exam.section.name else ""
        if section_name and len(section_name) == 1 and section_name.isalpha():
            return sanitize_filename_token(section_name)

        if exam.department_id is not None and exam.year_id is not None:
            standard_sections = (
                self.db.query(Section)
                .filter(
                    Section.department_id == exam.department_id,
                    Section.year_id == exam.year_id,
                )
                .all()
            )
            canonical = next(
                (
                    s.name.strip().upper()
                    for s in standard_sections
                    if len(s.name.strip()) == 1 and s.name.strip().isalpha()
                ),
                None,
            )
            if canonical:
                return sanitize_filename_token(canonical)

        return sanitize_filename_token(section_name or "SEC")

    def get_validated_report_data(self, exam_id: int) -> Dict[str, Any]:
        """
        Validates the exam state and executes the Phase 3 domain engine
        with require_complete=True to guarantee no incomplete or missing marks.
        Returns the canonical data package for report rendering.
        """
        exam = self.db.query(Exam).filter(Exam.id == exam_id).first()
        if not exam:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Exam with ID {exam_id} not found.",
            )

        questions = self.marks_service.get_exam_questions(exam_id)
        if not questions:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot generate report: Exam has no configured questions.",
            )

        enrolled_students = self.marks_service.get_exam_roster(exam_id)
        if not enrolled_students:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot generate report: No enrolled students found for the exam's configured section.",
            )

        saved_marks = self.marks_repo.get_by_exam(exam_id)
        if not saved_marks:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot generate report: No saved marks found for this exam. Please enter and save student marks before generating reports.",
            )

        co_codes = [c.co_code if hasattr(c, "co_code") else str(c) for c in (exam.covered_cos or [])]
        if not co_codes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot generate report: Exam has no covered COs configured.",
            )

        marks_list = [
            {
                "register_no": sm.student.register_no,
                "question_number": sm.question_number,
                "obtained_mark": float(sm.obtained_mark),
            }
            for sm in saved_marks
            if sm.student
        ]
        question_co_statistics = calculate_exam_co_statistics(questions, enrolled_students, marks_list)

        # Check cohort consistency
        enrolled_regs = {s["register_no"].strip().upper() for s in enrolled_students}
        for m in marks_list:
            if m["register_no"].strip().upper() not in enrolled_regs:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Cannot generate report: Student '{m['register_no']}' does not belong to the exam's configured class/section.",
                )

        # Execute Phase 3 calculation engine with strict completeness check
        try:
            domain_result = process_exam_marks_and_calculate(
                exam_id=exam.id,
                pass_percentage=float(exam.pass_percentage),
                covered_cos=co_codes,
                questions=questions,
                enrolled_students=enrolled_students,
                submitted_marks=marks_list,
                require_complete=True,
            )
        except IncompleteDataError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot generate report: {str(e)}",
            )
        except (DomainValidationError, CohortConsistencyError) as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot generate report: {str(e)}",
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot generate report: CO calculation error: {str(e)}",
            )

        # Build clean metadata
        dept_name = exam.department.name if exam.department else "N/A"
        dept_code = getattr(exam.department, "code", "")
        year_num = f"Year {exam.year.year_number}" if exam.year else "N/A"
        sem_num = f"Semester {exam.semester.semester_number}" if exam.semester else "N/A"
        sec_name = f"Section {exam.section.name}" if exam.section else "N/A"
        subj_name = exam.subject.name if exam.subject else "N/A"
        subj_code = getattr(exam.subject, "code", "")
        exam_date = exam.exam_date.strftime("%d-%m-%Y") if exam.exam_date else None

        # Deterministic base filename
        clean_subj = sanitize_filename_token(subj_name)
        clean_exam = sanitize_filename_token(exam.name)
        clean_sec = self._canonical_section_filename_token(exam)
        dept_code = sanitize_filename_token(getattr(exam.department, "code", "Department"))
        semester_number = getattr(exam.semester, "semester_number", "Semester")
        base_filename = (
            f"{dept_code}_Sem{semester_number}_{clean_sec}_{clean_subj}_{clean_exam}_CO_Attainment"
        )

        return {
            "exam_id": exam.id,
            "base_filename": base_filename,
            "metadata": {
                "department": f"{dept_name} ({dept_code})" if dept_code else dept_name,
                "year": year_num,
                "semester": sem_num,
                "section": sec_name,
                "subject": f"{subj_code} - {subj_name}" if subj_code else subj_name,
                "exam_name": exam.name,
                "exam_display": f"{exam.name} | Exam Date: {exam_date}" if exam_date else exam.name,
                "exam_date": exam_date,
                "pass_percentage": f"{float(exam.pass_percentage):.1f}%",
                "pass_percentage_val": float(exam.pass_percentage),
                "covered_cos": ", ".join(co_codes),
                "covered_cos_list": co_codes,
            },
            "questions": questions,
            "domain_result": domain_result,
            "question_co_statistics": question_co_statistics,
        }

    def generate_excel_report(self, exam_id: int) -> Tuple[io.BytesIO, str]:
        """
        Generates an authoritative, professional Excel (.xlsx) workbook for the exam.
        Contains top metadata block and detailed student marks & CO attainment results.
        """
        data = self.get_validated_report_data(exam_id)
        meta = data["metadata"]
        questions = data["questions"]
        domain_result = data["domain_result"]
        question_co_statistics = data["question_co_statistics"]
        covered_cos: List[str] = meta["covered_cos_list"]

        wb = Workbook()
        set_excel_monochrome_theme(wb)
        ws = wb.active
        ws.title = "CO Attainment Report"
        ws.sheet_view.showGridLines = False

        # Styles
        font_title = Font(name="Aptos Display", size=15, bold=True, color="000000")
        fill_title = PatternFill(start_color="FFFFFF", end_color="FFFFFF", fill_type="solid")

        font_meta_label = Font(name="Aptos", size=9, bold=True, color="000000")
        font_meta_val = Font(name="Aptos", size=9, color="000000")
        fill_meta = PatternFill(start_color="FFFFFF", end_color="FFFFFF", fill_type="solid")

        font_th = Font(name="Aptos", size=9, bold=True, color="000000")
        fill_th_main = PatternFill(start_color="FFFFFF", end_color="FFFFFF", fill_type="solid")
        fill_th_co = PatternFill(start_color="FFFFFF", end_color="FFFFFF", fill_type="solid")
        fill_alternate = PatternFill(start_color="FFFFFF", end_color="FFFFFF", fill_type="solid")

        font_data = Font(name="Aptos", size=9, color="000000")
        font_data_bold = Font(name="Aptos", size=9, bold=True, color="000000")

        border_thin = Border(
            left=Side(style="thin", color="000000"),
            right=Side(style="thin", color="000000"),
            top=Side(style="thin", color="000000"),
            bottom=Side(style="thin", color="000000"),
        )
        border_th = Border(
            left=Side(style="thin", color="000000"),
            right=Side(style="thin", color="000000"),
            top=Side(style="thin", color="000000"),
            bottom=Side(style="thin", color="000000"),
        )

        align_center = Alignment(horizontal="center", vertical="center", wrap_text=True)
        align_left = Alignment(horizontal="left", vertical="center")
        align_right = Alignment(horizontal="right", vertical="center")

        # Total column count: 2 (Reg No, Name) + len(questions) + 4 * len(covered_cos)
        num_q = len(questions)
        num_co = len(covered_cos)
        total_cols = 2 + num_q + (num_co * 4)

        # Report title (no logo image; preserve original document spacing)
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=total_cols)
        ws.row_dimensions[1].height = 10

        ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=total_cols)
        c_title = ws.cell(row=2, column=1, value="COURSE OUTCOME (CO) ATTAINMENT REPORT")
        c_title.font = font_title
        c_title.fill = fill_title
        c_title.alignment = align_center
        for col in range(1, total_cols + 1):
            ws.cell(row=2, column=col).fill = fill_title
        ws.row_dimensions[2].height = 30

        # Rows 3 - 5: Metadata Block
        meta_pairs = [
            ("Department:", meta["department"], "Subject:", meta["subject"]),
            ("Academic Year:", meta["year"], "Semester:", meta["semester"]),
            ("Section:", meta["section"], "Exam:", meta["exam_name"]),
            ("Exam Date:", meta["exam_date"], "Covered COs:", meta["covered_cos"]),
        ]

        for idx, (lbl1, val1, lbl2, val2) in enumerate(meta_pairs, start=3):
            ws.row_dimensions[idx].height = 22
            # Col 1 & 2
            c_l1 = ws.cell(row=idx, column=1, value=lbl1)
            c_l1.font = font_meta_label
            c_l1.fill = fill_meta
            c_l1.alignment = align_left

            # Val 1 spans questions if enough space
            half_cols = max(3, (total_cols // 2))
            ws.merge_cells(start_row=idx, start_column=2, end_row=idx, end_column=half_cols)
            c_v1 = ws.cell(row=idx, column=2, value=val1)
            c_v1.font = font_meta_val
            c_v1.fill = fill_meta
            c_v1.alignment = align_left

            c_l2 = ws.cell(row=idx, column=half_cols + 1, value=lbl2)
            c_l2.font = font_meta_label
            c_l2.fill = fill_meta
            c_l2.alignment = align_left

            ws.merge_cells(start_row=idx, start_column=half_cols + 2, end_row=idx, end_column=total_cols)
            c_v2 = ws.cell(row=idx, column=half_cols + 2, value=val2)
            c_v2.font = font_meta_val
            c_v2.fill = fill_meta
            c_v2.alignment = align_left

            # Borders for metadata row
            for col in range(1, total_cols + 1):
                ws.cell(row=idx, column=col).border = border_thin

        # Row 7: Top-level student, question, and CO-result groups
        ws.row_dimensions[7].height = 22
        ws.merge_cells(start_row=7, start_column=1, end_row=7, end_column=2)
        student_band = ws.cell(row=7, column=1, value="STUDENT INFORMATION")
        student_band.fill = fill_th_main
        student_band.font = font_th
        student_band.alignment = align_center
        question_start = 3
        question_end = 2 + num_q
        if num_q:
            ws.merge_cells(start_row=7, start_column=question_start, end_row=7, end_column=question_end)
            question_band = ws.cell(row=7, column=question_start, value="QUESTION MARKS")
            question_band.fill = fill_th_main
            question_band.font = font_th
            question_band.alignment = align_center
        if num_co:
            co_start = question_end + 1
            ws.merge_cells(start_row=7, start_column=co_start, end_row=7, end_column=total_cols)
            co_band = ws.cell(row=7, column=co_start, value="CO RESULTS")
            co_band.fill = fill_th_co
            co_band.font = font_th
            co_band.alignment = align_center

        # Rows 8 & 9: Multi-level table headers
        ws.row_dimensions[8].height = 25
        ws.row_dimensions[9].height = 30

        # Register Number (Row 7-8 merged)
        ws.merge_cells(start_row=8, start_column=1, end_row=9, end_column=1)
        c = ws.cell(row=8, column=1, value="Register Number")
        c.font = font_th
        c.fill = fill_th_main
        c.alignment = align_center

        # Student Name (Row 7-8 merged)
        ws.merge_cells(start_row=8, start_column=2, end_row=9, end_column=2)
        c = ws.cell(row=8, column=2, value="Student Name")
        c.font = font_th
        c.fill = fill_th_main
        c.alignment = align_center

        # Question Columns (Row 7 & 8)
        current_col = 3
        for q in questions:
            q_num = q["question_number"]
            max_m = float(q["max_marks"])
            co_code = q["co_code"]

            # Row 7: Question Number
            c7 = ws.cell(row=8, column=current_col, value=q_num)
            c7.font = font_th
            c7.fill = fill_th_main
            c7.alignment = align_center

            # Row 8: Max Marks & mapped CO
            c8 = ws.cell(row=9, column=current_col, value=f"Max: {max_m:g}\n({co_code})")
            c8.font = Font(name="Calibri", size=9, bold=True, color="000000")
            c8.fill = fill_th_main
            c8.alignment = align_center

            current_col += 1

        # CO Group Columns (Row 7 & 8)
        for co in covered_cos:
            start_co_col = current_col
            end_co_col = current_col + 3

            # Row 7: Merged CO Group Header
            ws.merge_cells(start_row=8, start_column=start_co_col, end_row=8, end_column=end_co_col)
            c_co = ws.cell(row=8, column=start_co_col, value=f"{co} Results")
            c_co.font = font_th
            c_co.fill = fill_th_co
            c_co.alignment = align_center

            # Row 8: 4 Subheaders
            subheaders = [
                ("Max Marks", fill_th_co),
                ("Obtained Marks", fill_th_co),
                ("CO %", fill_th_co),
                ("CO Attainment", fill_th_co),
            ]
            for offset, (sh_text, sh_fill) in enumerate(subheaders):
                c_sh = ws.cell(row=9, column=start_co_col + offset, value=sh_text)
                c_sh.font = font_th
                c_sh.fill = sh_fill
                c_sh.alignment = align_center

            current_col += 4

        # Apply borders to all header cells
        for r in (7, 8, 9):
            for col in range(1, total_cols + 1):
                ws.cell(row=r, column=col).border = border_th

        # Data Rows (Row 10 onwards)
        row_idx = 10
        for s in domain_result.students:
            ws.row_dimensions[row_idx].height = 20
            row_fill = fill_alternate if row_idx % 2 == 0 else PatternFill(fill_type=None)

            # Col 1: Register No
            c_reg = ws.cell(row=row_idx, column=1, value=s.register_no)
            c_reg.font = font_data_bold
            c_reg.alignment = align_center
            c_reg.border = border_thin
            c_reg.fill = row_fill

            # Col 2: Student Name
            c_name = ws.cell(row=row_idx, column=2, value=s.name)
            c_name.font = font_data
            c_name.alignment = align_left
            c_name.border = border_thin
            c_name.fill = row_fill

            # Question marks
            col_ptr = 3
            for q in questions:
                q_num = q["question_number"]
                mark_val = s.question_marks.get(q_num, 0.0)
                c_m = ws.cell(row=row_idx, column=col_ptr, value=float(mark_val))
                c_m.font = font_data
                c_m.alignment = align_right
                c_m.border = border_thin
                c_m.fill = row_fill
                c_m.number_format = "#,##0.0"
                col_ptr += 1

            # CO Results
            for co in covered_cos:
                co_res = s.co_results.get(co)
                if co_res:
                    co_max = float(co_res.co_max_marks)
                    co_obt = float(co_res.obtained_marks)
                    co_pct = float(co_res.co_percentage)
                    co_att = int(co_res.attainment)  # Strictly numeric 1 or 0
                else:
                    co_max, co_obt, co_pct, co_att = 0.0, 0.0, 0.0, 0

                # Max
                c_max = ws.cell(row=row_idx, column=col_ptr, value=co_max)
                c_max.font = font_data
                c_max.alignment = align_right
                c_max.border = border_thin
                c_max.fill = row_fill
                c_max.number_format = "#,##0.0"

                # Obtained
                c_obt = ws.cell(row=row_idx, column=col_ptr + 1, value=co_obt)
                c_obt.font = font_data
                c_obt.alignment = align_right
                c_obt.border = border_thin
                c_obt.fill = row_fill
                c_obt.number_format = "#,##0.0"

                # Percentage
                c_pct = ws.cell(row=row_idx, column=col_ptr + 2, value=co_pct)
                c_pct.font = font_data
                c_pct.alignment = align_right
                c_pct.border = border_thin
                c_pct.fill = row_fill
                c_pct.number_format = "0.0\"%\""

                # Attainment: STRICT NUMERIC 1 or 0
                c_att = ws.cell(row=row_idx, column=col_ptr + 3, value=co_att)
                c_att.font = font_data_bold
                c_att.alignment = align_center
                c_att.border = border_thin
                c_att.fill = row_fill
                c_att.number_format = "0"

                col_ptr += 4

            row_idx += 1

        statistics_labels = [
            ("NO OF STUDENTS >= 50% MARKS", "students_at_least_50_percent", False),
            ("NO OF STUDENTS ATTEMPTED", "students_attempted", False),
            ("% STUDENTS >= 50% MARKS", "percentage_at_least_50_percent", True),
        ]
        statistics_by_question = {
            row["question_number"]: row for row in question_co_statistics["questions"]
        }
        statistics_row = row_idx
        for label, key, is_percentage in statistics_labels:
            ws.merge_cells(start_row=statistics_row, start_column=1, end_row=statistics_row, end_column=2)
            label_cell = ws.cell(row=statistics_row, column=1, value=label)
            label_cell.font = font_data_bold
            label_cell.alignment = align_left
            for col_idx in range(1, total_cols + 1):
                cell = ws.cell(row=statistics_row, column=col_idx)
                cell.border = border_thin
                cell.fill = fill_alternate
            for question_index, question in enumerate(questions, start=3):
                value = statistics_by_question[question["question_number"]][key]
                cell = ws.cell(row=statistics_row, column=question_index, value=value)
                cell.font = font_data
                cell.alignment = align_center
                if is_percentage and value is not None:
                    cell.number_format = '0.00"%"'
            statistics_row += 1

        for average in question_co_statistics["co_averages"]:
            ws.merge_cells(start_row=statistics_row, start_column=1, end_row=statistics_row, end_column=2)
            label_cell = ws.cell(row=statistics_row, column=1, value=f"AVERAGE OF {average['co_code']}")
            label_cell.font = font_data_bold
            label_cell.alignment = align_left
            for col_idx in range(1, total_cols + 1):
                cell = ws.cell(row=statistics_row, column=col_idx)
                cell.border = border_thin
                cell.fill = fill_alternate
            average_cell = ws.cell(row=statistics_row, column=3, value=average["average_percentage"])
            average_cell.font = font_data_bold
            average_cell.alignment = align_center
            if average["average_percentage"] is not None:
                average_cell.number_format = '0.00"%"'
            statistics_row += 1

        summary_start = statistics_row + 1
        ws.cell(row=summary_start, column=1, value="Overall CO Attainment Summary")
        ws.merge_cells(start_row=summary_start, start_column=1, end_row=summary_start, end_column=5)
        summary_title = ws.cell(row=summary_start, column=1)
        summary_title.font = font_title
        summary_title.fill = fill_title
        summary_title.alignment = align_left
        for col_idx in range(1, 6):
            ws.cell(row=summary_start, column=col_idx).fill = fill_title
        summary_headers = ["CO", "Total Students", "Students Attaining", "Attainment %", "Overall Level"]
        for col_idx, header in enumerate(summary_headers, start=1):
            cell = ws.cell(row=summary_start + 1, column=col_idx, value=header)
            cell.font = font_th
            cell.fill = fill_th_co
            cell.border = border_th
            cell.alignment = align_center
        for offset, co in enumerate(covered_cos, start=summary_start + 2):
            ws.row_dimensions[offset].height = 20
            summary = domain_result.overall_co_attainment[co]
            values = [
                co,
                summary.total_students,
                summary.students_attaining_co,
                float(summary.attainment_percentage),
                summary.attainment_level if summary.attainment_level is not None else "Unresolved",
            ]
            for col_idx, value in enumerate(values, start=1):
                cell = ws.cell(row=offset, column=col_idx, value=value)
                cell.border = border_thin
                cell.alignment = align_center
                cell.font = font_data
                if offset % 2 == 0:
                    cell.fill = fill_alternate
            ws.cell(row=offset, column=4).number_format = '0.0"%"'

        # Auto-fit column widths
        col_min_widths = {
            1: 16,  # Register Number
            2: 24,  # Student Name
        }
        for col_idx in range(1, total_cols + 1):
            col_letter = get_column_letter(col_idx)
            if col_idx in col_min_widths:
                ws.column_dimensions[col_letter].width = col_min_widths[col_idx]
            elif col_idx <= 2 + num_q:
                ws.column_dimensions[col_letter].width = 12  # Questions
            else:
                ws.column_dimensions[col_letter].width = 14  # CO Columns

        # Keep the sheet easy to scroll and print without an awkward frozen dashboard layout.
        ws.freeze_panes = None
        ws.sheet_properties.pageSetUpPr.fitToPage = True
        ws.page_setup.orientation = "landscape"
        ws.page_setup.paperSize = ws.PAPERSIZE_A3
        ws.page_setup.fitToWidth = 1
        ws.page_setup.fitToHeight = 0
        ws.page_margins.left = 0.25
        ws.page_margins.right = 0.25
        ws.page_margins.top = 0.5
        ws.page_margins.bottom = 0.45
        ws.print_title_rows = None
        summary_end = summary_start + 1 + len(covered_cos)
        ws.print_area = None

        stream = io.BytesIO()
        wb.save(stream)
        stream.seek(0)
        filename = f"{data['base_filename']}.xlsx"
        return stream, filename

    def generate_pdf_report(self, exam_id: int) -> Tuple[io.BytesIO, str]:
        """
        Generates an authoritative, clean, printable PDF report in landscape orientation.
        Uses ReportLab with automatic multi-page repeating table headers.
        """
        data = self.get_validated_report_data(exam_id)
        meta = data["metadata"]
        questions = data["questions"]
        domain_result = data["domain_result"]
        question_co_statistics = data["question_co_statistics"]
        covered_cos: List[str] = meta["covered_cos_list"]

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=landscape(A2),
            leftMargin=38,
            rightMargin=38,
            topMargin=86,
            bottomMargin=34,
            title="Course Outcome (CO) Attainment Report",
        )

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            "ExamReportTitle",
            parent=styles["Title"],
            fontName="Helvetica-Bold",
            fontSize=15,
            leading=18,
            textColor=colors.black,
            alignment=1,
            spaceAfter=7,
        )
        section_style = ParagraphStyle(
            "ExamReportSection",
            parent=styles["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=14,
            textColor=colors.black,
            spaceBefore=5,
            spaceAfter=5,
        )
        meta_label_style = ParagraphStyle(
            "ExamMetaLabel",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=10,
            textColor=colors.black,
        )
        meta_val_style = ParagraphStyle(
            "ExamMetaValue",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=8,
            leading=10,
            textColor=colors.black,
        )
        th_style = ParagraphStyle(
            "ExamTableHeader",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=7.2,
            leading=8.5,
            alignment=1,
            textColor=colors.black,
        )
        subheader_style = ParagraphStyle(
            "ExamTableSubheader",
            parent=th_style,
            textColor=colors.black,
        )
        cell_center = ParagraphStyle(
            "ExamCellCenter",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=7.2,
            leading=8.5,
            alignment=1,
            textColor=colors.black,
        )
        cell_bold_center = ParagraphStyle(
            "ExamCellBoldCenter",
            parent=cell_center,
            fontName="Helvetica-Bold",
        )
        cell_left = ParagraphStyle(
            "ExamCellLeft",
            parent=cell_center,
            alignment=0,
        )
        cell_right = ParagraphStyle(
            "ExamCellRight",
            parent=cell_center,
            alignment=2,
        )

        story = [
            Paragraph("COURSE OUTCOME (CO) ATTAINMENT REPORT", title_style),
        ]

        meta_rows = [
            ("Department", meta["department"], "Academic Year", meta["year"]),
            ("Semester", meta["semester"], "Section", meta["section"]),
            ("Subject", meta["subject"], "Exam", meta["exam_display"]),
            ("Pass Percentage", meta["pass_percentage"], "Covered COs", meta["covered_cos"]),
        ]
        meta_table_data = [
            [
                Paragraph(escape(label1), meta_label_style),
                Paragraph(escape(value1), meta_val_style),
                Paragraph(escape(label2), meta_label_style),
                Paragraph(escape(value2), meta_val_style),
            ]
            for label1, value1, label2, value2 in meta_rows
        ]
        label_width = 102
        value_width = (doc.width - (2 * label_width)) / 2
        meta_table = Table(
            meta_table_data,
            colWidths=[label_width, value_width, label_width, value_width],
        )
        meta_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.white),
            ("BOX", (0, 0), (-1, -1), 0.75, colors.black),
            ("INNERGRID", (0, 0), (-1, -1), 0.45, colors.black),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 7),
            ("RIGHTPADDING", (0, 0), (-1, -1), 7),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.extend([meta_table, Spacer(1, 10), Paragraph("STUDENT MARKS &amp; CO RESULTS", section_style)])

        num_q = len(questions)
        num_co = len(covered_cos)
        student_band = [Paragraph("STUDENT INFORMATION", th_style), ""]
        if num_q:
            student_band.append(Paragraph("QUESTION MARKS", th_style))
            student_band.extend([""] * (num_q - 1))
        for co in covered_cos:
            student_band.extend([Paragraph("COURSE OUTCOME RESULTS", th_style), "", "", ""])

        group_headers = [
            Paragraph("Register Number", subheader_style),
            Paragraph("Student Name", subheader_style),
        ]
        for question in questions:
            group_headers.append(Paragraph(escape(str(question["question_number"])), subheader_style))
        for co in covered_cos:
            group_headers.extend([Paragraph(f"{escape(co)} Results", th_style), "", "", ""])

        detail_headers = ["", ""]
        for question in questions:
            max_marks = float(question["max_marks"])
            detail_headers.append(Paragraph(
                f"Max: {max_marks:g}<br/>({escape(question['co_code'])})",
                subheader_style,
            ))
        for _ in covered_cos:
            detail_headers.extend([
                Paragraph("Max Marks", subheader_style),
                Paragraph("Obtained", subheader_style),
                Paragraph("CO %", subheader_style),
                Paragraph("Attainment", subheader_style),
            ])

        table_rows = [student_band, group_headers, detail_headers]
        for student in domain_result.students:
            student_row = [
                Paragraph(escape(student.register_no), cell_bold_center),
                Paragraph(escape(student.name), cell_left),
            ]
            for question in questions:
                mark = student.question_marks.get(question["question_number"], 0.0)
                student_row.append(Paragraph(f"{float(mark):.1f}", cell_right))

            for co in covered_cos:
                co_result = student.co_results.get(co)
                if co_result:
                    co_max = float(co_result.co_max_marks)
                    co_obtained = float(co_result.obtained_marks)
                    co_percentage = float(co_result.co_percentage)
                    co_attainment = int(co_result.attainment)
                else:
                    co_max, co_obtained, co_percentage, co_attainment = 0.0, 0.0, 0.0, 0
                student_row.extend([
                    Paragraph(f"{co_max:.1f}", cell_right),
                    Paragraph(f"{co_obtained:.1f}", cell_right),
                    Paragraph(f"{co_percentage:.1f}%", cell_right),
                    Paragraph(str(co_attainment), cell_bold_center),
                ])
            table_rows.append(student_row)

        question_count = num_q
        statistics_by_question = {
            row["question_number"]: row for row in question_co_statistics["questions"]
        }
        for label, key, is_percentage in [
            ("NO OF STUDENTS >= 50% MARKS", "students_at_least_50_percent", False),
            ("NO OF STUDENTS ATTEMPTED", "students_attempted", False),
            ("% STUDENTS >= 50% MARKS", "percentage_at_least_50_percent", True),
        ]:
            row = [Paragraph(label, cell_bold_center), ""]
            for question in questions:
                value = statistics_by_question[question["question_number"]][key]
                display = f"{value:.2f}%" if is_percentage and value is not None else ("" if value is None else str(value))
                row.append(Paragraph(display, cell_center))
            row.extend([""] * (num_co * 4))
            table_rows.append(row)

        for average in question_co_statistics["co_averages"]:
            row = [Paragraph(f"AVERAGE OF {escape(average['co_code'])}", cell_bold_center), ""]
            display = f"{average['average_percentage']:.2f}%" if average["average_percentage"] is not None else ""
            row.append(Paragraph(display, cell_bold_center))
            row.extend([""] * (num_q - 1 + num_co * 4))
            table_rows.append(row)

        co_start_col = 2 + question_count
        table_style = [
            ("SPAN", (0, 0), (1, 0)),
            ("SPAN", (0, 1), (0, 2)),
            ("SPAN", (1, 1), (1, 2)),
            ("BACKGROUND", (0, 0), (1, 0), colors.white),
            ("BACKGROUND", (2, 0), (1 + question_count, 0), colors.white),
            ("BACKGROUND", (0, 1), (-1, 1), colors.white),
            ("BACKGROUND", (0, 2), (-1, 2), colors.white),
            ("BOX", (0, 0), (-1, -1), 0.75, colors.black),
            ("INNERGRID", (0, 0), (-1, -1), 0.45, colors.black),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 0), (-1, 2), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 3),
            ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ]
        for co_index in range(num_co):
            co_col = co_start_col + (co_index * 4)
            table_style.extend([
                ("SPAN", (co_col, 1), (co_col + 3, 1)),
                ("BACKGROUND", (co_col, 1), (co_col + 3, 1), colors.white),
            ])
        for row_index in range(3, len(table_rows)):
            if (row_index - 3) % 2 == 1:
                table_style.append(("BACKGROUND", (0, row_index), (-1, row_index), colors.white))
        statistics_start_row = 3 + len(domain_result.students)
        for row_index in range(statistics_start_row, len(table_rows)):
            table_style.extend([
                ("SPAN", (0, row_index), (1, row_index)),
                ("BACKGROUND", (0, row_index), (-1, row_index), colors.white),
                ("FONTNAME", (0, row_index), (-1, row_index), "Helvetica-Bold"),
            ])

        base_widths = [92, 165]
        other_columns = num_q + (num_co * 4)
        other_width = (doc.width - sum(base_widths)) / max(1, other_columns)
        column_widths = [*base_widths, *([other_width] * other_columns)]
        results_table = Table(table_rows, colWidths=column_widths, repeatRows=3, hAlign="LEFT")
        results_table.setStyle(TableStyle(table_style))
        story.append(results_table)

        summary_rows = [[
            Paragraph("CO", th_style),
            Paragraph("Total Students", th_style),
            Paragraph("Students Attaining", th_style),
            Paragraph("Attainment %", th_style),
            Paragraph("Overall Level", th_style),
        ]]
        for co in covered_cos:
            summary = domain_result.overall_co_attainment[co]
            level = str(summary.attainment_level) if summary.attainment_level is not None else "Unresolved"
            summary_rows.append([
                Paragraph(escape(co), cell_bold_center),
                Paragraph(str(summary.total_students), cell_center),
                Paragraph(str(summary.students_attaining_co), cell_center),
                Paragraph(f"{float(summary.attainment_percentage):.1f}%", cell_right),
                Paragraph(escape(level), cell_center),
            ])
        story.extend([Spacer(1, 10), Paragraph("OVERALL CO ATTAINMENT SUMMARY", section_style)])
        summary_widths = [90, 135, 155, 130, 150]
        summary_table = Table(summary_rows, colWidths=summary_widths, repeatRows=1, hAlign="LEFT")
        summary_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.white),
            ("BOX", (0, 0), (-1, -1), 0.75, colors.black),
            ("INNERGRID", (0, 0), (-1, -1), 0.45, colors.black),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(summary_table)

        doc.build(
            story,
            canvasmaker=NumberedCanvas,
        )
        buffer.seek(0)
        filename = f"{data['base_filename']}.pdf"
        return buffer, filename
