import fitz
from io import BytesIO
import logging

def extract_page_tables_with_bboxes(pdf_path, page_number):

    if isinstance(pdf_path, bytes):
        logging.info("__table_parse__found_bytes")
        stream = BytesIO(pdf_path)
        doc = fitz.open(stream=stream, filetype="pdf")
    else:
        logging.info("__table_parse__found_filepath")
        doc = fitz.open(pdf_path)

    page = doc.load_page(page_number)

    tabs = page.find_tables()

    return tabs.tables