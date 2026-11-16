from io import BytesIO
from pathlib import Path
import re

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from PIL import Image

from app.db.models import Section, Subject
from app.db.session import SessionLocal
from app.main import app

client = TestClient(app)


def _subject_id() -> int:
    with SessionLocal() as db:
        subject = db.query(Subject).filter(Subject.is_active.is_(True)).order_by(Subject.id).first()
        assert subject is not None
        return subject.id


def _subject_metadata(subject_id: int) -> dict[str, str]:
    with SessionLocal() as db:
        subject = db.query(Subject).filter(Subject.id == subject_id).first()
        assert subject is not None
        return {
            "department": subject.department.name,
            "year": subject.year.name,
            "semester": subject.semester.name,
            "subject": subject.name,
        }


def _section_id(subject_id: int, section_name: str = "A") -> int:
    with SessionLocal() as db:
        subject = db.query(Subject).filter(Subject.id == subject_id).one()
        return db.query(Section).filter_by(
            department_id=subject.department_id,
            year_id=subject.year_id,
            name=section_name,
        ).one().id


def _empty_inputs():
    return [
        {"a": None, "b": None, "c": None, "university": None, "g": None}
        for _ in range(5)
    ]


@pytest.fixture
def saved_course_obe_data():
    subject_id = _subject_id()
    section_id = _section_id(subject_id)
    base_url = f"/api/course-obe/subjects/{subject_id}"
    mapping_url = f"{base_url}/co-po-mapping?section_id={section_id}"
    overall_url = f"{base_url}/overall-co-attainment?section_id={section_id}"
    initial_mapping = client.get(mapping_url).json()["values"]
    initial_inputs = client.get(overall_url).json()["inputs"]

    mappings = [[None for _ in range(14)] for _ in range(5)]
    mappings[0][0] = 3
    mappings[0][1] = 2
    inputs = _empty_inputs()
    inputs[0] = {"a": 93.5, "b": 94, "c": 94.5, "university": 90, "g": 3}
    assert client.put(mapping_url, json={"values": mappings}).status_code == 200
    assert client.put(overall_url, json={"inputs": inputs}).status_code == 200

    yield subject_id, section_id

    client.put(mapping_url, json={"values": initial_mapping})
    client.put(overall_url, json={"inputs": initial_inputs})


def test_course_obe_excel_report_uses_saved_data_and_contains_all_tables(saved_course_obe_data):
    subject_id, section_id = saved_course_obe_data
    metadata = _subject_metadata(subject_id)
    response = client.get(f"/api/course-obe/subjects/{subject_id}/report/excel?section_id={section_id}")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert response.headers["content-disposition"].endswith('.xlsx"')

    workbook = load_workbook(BytesIO(response.content), data_only=True)
    worksheet = workbook["Course OBE Analysis"]
    assert worksheet["A1"].value is None
    assert worksheet["A2"].value == "COURSE OBE ANALYSIS REPORT"
    assert len(worksheet._images) == 1
    logo_path = Path(__file__).resolve().parents[2] / "src" / "assets" / "institute-header.png.jpeg.png"
    with Image.open(logo_path) as logo:
        assert (worksheet._images[0].width, worksheet._images[0].height) == logo.size
        assert worksheet._images[0].width / worksheet._images[0].height == pytest.approx(logo.width / logo.height)
    assert worksheet.row_dimensions[1].height == 60
    assert worksheet.sheet_view.showGridLines is False
    assert worksheet.page_setup.orientation == "landscape"
    assert str(worksheet.page_setup.paperSize) == worksheet.PAPERSIZE_A3
    assert worksheet.print_area == "'Course OBE Analysis'!$A$1:$N$33"
    assert [worksheet.cell(row=row, column=1).value for row in range(4, 9)] == [
        "Department", "Academic Year", "Semester", "Section", "Subject"
    ]
    assert [worksheet.cell(row=row, column=2).value for row in range(4, 9)] == [
        metadata["department"], metadata["year"], metadata["semester"], "A", metadata["subject"]
    ]
    assert worksheet["A10"].value == "1. CO-PO Mapping"
    assert [worksheet.cell(row=11, column=column).value for column in (1, 2, 3, 13, 14)] == [
        "CO", "PO1", "PO2", "PSO1", "PSO2"
    ]
    assert all(
        "PO12" not in str(value)
        for row in worksheet.iter_rows(min_row=11, max_row=33, min_col=1, max_col=15)
        for value in (cell.value for cell in row)
        if value is not None
    )
    assert worksheet["A12"].value == "CO1"
    assert worksheet["B12"].value == 3
    assert worksheet["C12"].value == 2

    assert worksheet["A18"].value == "2. Computation of Overall CO Attainment in this Course"
    assert [worksheet.cell(row=19, column=column).value for column in range(1, 16)] == [
        "CO", "A (INT1)", "B (INT2)", "C (MODEL)", "Average", "Attainment", "University",
        "Attainment", "D (20%)", "E (80%)", "F", "90% of F", "G", "10% of G", "Overall CO",
    ]
    assert [worksheet.cell(row=20, column=column).value for column in range(1, 16)] == [
        "CO1", 93.5, 94, 94.5, 94, 3, 90, 3, 0.6, 2.4, 3, 2.7, 3, 0.3, 3,
    ]
    assert worksheet["B20"].number_format == "0.##"
    assert worksheet["E20"].number_format == "0.00"

    assert worksheet["A26"].value == "3. PO Attainment"
    assert [worksheet.cell(row=27, column=column).value for column in (1, 2, 3, 13, 14)] == [
        "CO", "PO1", "PO2", "PSO1", "PSO2"
    ]
    assert b"PO12" not in response.content
    assert worksheet["B28"].value == 3
    assert worksheet["C28"].value == 2
    assert worksheet["D28"].value == "-"
    assert [worksheet.cell(row=33, column=column).value for column in (1, 2, 3, 13, 14)] == [
        "Overall", 3, 2, None, None
    ]
    assert worksheet["B33"].font.bold is True
    assert worksheet["B33"].fill.fgColor.rgb in ("00000000", "00FFFFFF")


def test_course_obe_reports_read_only_the_requested_section(saved_course_obe_data):
    subject_id, section_a_id = saved_course_obe_data
    section_b_id = _section_id(subject_id, "B")
    response_a = client.get(
        f"/api/course-obe/subjects/{subject_id}/report/excel?section_id={section_a_id}"
    )
    response_b = client.get(
        f"/api/course-obe/subjects/{subject_id}/report/excel?section_id={section_b_id}"
    )
    assert response_a.status_code == response_b.status_code == 200

    worksheet_a = load_workbook(BytesIO(response_a.content), data_only=True)["Course OBE Analysis"]
    worksheet_b = load_workbook(BytesIO(response_b.content), data_only=True)["Course OBE Analysis"]
    assert worksheet_a["B7"].value == "A"
    assert worksheet_b["B7"].value == "B"
    assert worksheet_a["B12"].value == 3
    assert worksheet_a["B20"].value == 93.5
    assert worksheet_b["B12"].value == "-"
    assert worksheet_b["B20"].value is None


def test_course_obe_report_exports_page_po_overall_values(saved_course_obe_data):
    subject_id, section_id = saved_course_obe_data
    mapping_url = f"/api/course-obe/subjects/{subject_id}/co-po-mapping?section_id={section_id}"
    overall_url = f"/api/course-obe/subjects/{subject_id}/overall-co-attainment?section_id={section_id}"
    po_url = f"/api/course-obe/subjects/{subject_id}/po-attainment?section_id={section_id}"

    mappings = [[None for _ in range(14)] for _ in range(5)]
    mappings[0][0] = 3
    mappings[0][1] = 2
    mappings[0][12] = 1
    mappings[1][0] = 2
    mappings[1][1] = 2
    mappings[1][12] = 3
    inputs = _empty_inputs()
    inputs[0] = {"a": 93.5, "b": 94, "c": 94.5, "university": 90, "g": 3}
    inputs[1] = inputs[0].copy()
    assert client.put(mapping_url, json={"values": mappings}).status_code == 200
    assert client.put(overall_url, json={"inputs": inputs}).status_code == 200
    page_values = client.get(po_url).json()
    expected_overall = page_values["overall_values"]
    assert expected_overall[:2] == pytest.approx([2.5, 2])
    assert expected_overall[12] == pytest.approx(2)
    assert expected_overall[13] is None
    visible_expected_overall = [value for index, value in enumerate(expected_overall) if index != 11]

    excel_response = client.get(f"/api/course-obe/subjects/{subject_id}/report/excel?section_id={section_id}")
    assert excel_response.status_code == 200
    worksheet = load_workbook(BytesIO(excel_response.content), data_only=True)["Course OBE Analysis"]
    assert [worksheet.cell(row=row, column=1).value for row in range(28, 34)] == [
        "CO1", "CO2", "CO3", "CO4", "CO5", "Overall"
    ]
    for column_index, expected in enumerate(visible_expected_overall, start=2):
        exported = worksheet.cell(row=33, column=column_index).value
        if expected is None:
            assert exported is None
        else:
            assert exported == pytest.approx(expected)
            assert worksheet.cell(row=33, column=column_index).number_format == "0.00"
    for row_index in range(5):
        visible_row = [value for column_index, value in enumerate(mappings[row_index]) if column_index != 11]
        visible_page_row = [value for column_index, value in enumerate(page_values["values"][row_index]) if column_index != 11]
        for column_index, expected in enumerate(visible_row, start=2):
            exported = worksheet.cell(row=row_index + 28, column=column_index).value
            if expected is None:
                assert exported == "-"
            else:
                assert exported == pytest.approx(visible_page_row[column_index - 2])

    pdf_response = client.get(f"/api/course-obe/subjects/{subject_id}/report/pdf?section_id={section_id}")
    assert pdf_response.status_code == 200
    assert b"PO12" not in pdf_response.content
    for expected in expected_overall:
        if expected is not None:
            assert f"{expected:.2f}".encode() in pdf_response.content
    assert b"2.50" in pdf_response.content


def test_course_obe_pdf_report_is_landscape_and_contains_all_tables(saved_course_obe_data):
    subject_id, section_id = saved_course_obe_data
    metadata = _subject_metadata(subject_id)
    response = client.get(f"/api/course-obe/subjects/{subject_id}/report/pdf?section_id={section_id}")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"].endswith('.pdf"')
    assert response.content.startswith(b"%PDF-")
    assert len(re.findall(rb"/Type\s*/Page\b", response.content)) == 3
    for content in (
        b"COURSE OBE ANALYSIS REPORT",
        b"CO-PO Mapping",
        b"Computation of Overall CO Attainment in this Course",
        b"PO Attainment",
        b"3.00",
        b"2.00",
        b"93",
        b"94",
        b"Section",
        b"A",
        b"OBE Exam Analysis",
        b"Page 1 of 3",
    ):
        assert content in response.content
    for value in metadata.values():
        assert value.encode() in response.content