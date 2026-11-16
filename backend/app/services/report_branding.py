import io
from pathlib import Path
from xml.etree import ElementTree

from openpyxl.drawing.image import Image as ExcelImage
from openpyxl.styles import Font
from openpyxl.writer.theme import theme_xml
from openpyxl.worksheet.worksheet import Worksheet
from PIL import Image, ImageOps
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

APPLICATION_NAME = "OBE Exam Analysis System"
BLACK = "000000"
WHITE = "FFFFFF"
NAVY = "000000"
BLUE = "000000"
LIGHT_BLUE = "F8F8F8"
PALE_BLUE = "FFFFFF"
LIGHT_GREY = "F5F5F5"
MID_GREY = "7A7A7A"
DARK_GREY = "1F1F1F"
LOGO_PATH = Path(__file__).resolve().parents[3] / "src" / "assets" / "institute-header.png.jpeg.png"


def set_excel_monochrome_theme(workbook) -> None:
    workbook._fonts[0] = Font(name="Calibri", size=11, family=2, scheme="minor", color="FF000000")
    namespace = "http://schemas.openxmlformats.org/drawingml/2006/main"
    ElementTree.register_namespace("a", namespace)
    root = ElementTree.fromstring(theme_xml)
    color_scheme = root.find(f".//{{{namespace}}}clrScheme")
    if color_scheme is not None:
        for color_slot in color_scheme:
            color_slot.clear()
            color = "FFFFFF" if color_slot.tag.rsplit("}", 1)[-1] in ("lt1", "lt2") else "000000"
            ElementTree.SubElement(color_slot, f"{{{namespace}}}srgbClr", {"val": color})

    for element in root.iter():
        element_name = element.tag.rsplit("}", 1)[-1]
        if element_name == "srgbClr" and element.get("val", "").upper() not in ("000000", "FFFFFF"):
            element.set("val", "000000")
        elif element_name == "sysClr":
            element.set("lastClr", "000000")
        elif element_name == "prstClr" and element.get("val", "").lower() != "white":
            element.set("val", "black")

    workbook.loaded_theme = ElementTree.tostring(root, encoding="utf-8", xml_declaration=True)


def add_excel_logo(worksheet: Worksheet, anchor: str = "A1", width: int = 640, height: int = 80) -> None:
    """No-op: exported reports must remain text-only without any logo image."""
    return None


def draw_college_page_header(pdf_canvas: canvas.Canvas, document) -> None:
    """No-op: exported PDFs omit the institute logo and logo header artwork."""
    return None


class NumberedCanvas(canvas.Canvas):
    """ReportLab canvas that adds consistent page numbering after pagination."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        page_count = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self._draw_footer(page_count)
            super().showPage()
        super().save()

    def _draw_footer(self, page_count: int) -> None:
        page_width, _ = self._pagesize
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.black)
        self.drawString(32, 18, APPLICATION_NAME)
        self.drawRightString(page_width - 32, 18, f"Page {self._pageNumber} of {page_count}")
        self.restoreState()