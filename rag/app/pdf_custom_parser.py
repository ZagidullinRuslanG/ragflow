#
#  Custom PDF parser utilities for pdfminer-based layout analysis
#  with Russian-specific text classification and image mosaicking.
#
#  Ported from the original fork's manual.py and naive.py.
#

import hashlib
import io
import logging
import re
from io import BytesIO
from typing import BinaryIO, Container, Iterable, Iterator, List, Literal, Optional, Sequence, Tuple, Union

import numpy as np
import pandas as pd
from PIL import Image, ImageChops, ImageOps
from pdfminer.converter import PDFPageAggregator
from pdfminer.high_level import extract_pages
from pdfminer.layout import (
    LAParams,
    LTChar,
    LTFigure,
    LTImage,
    LTPage,
    LTTextBox,
    LTTextContainer,
    LTTextLine,
)
from pdfminer.pdfcolor import LITERAL_DEVICE_CMYK
from pdfminer.pdfdocument import PDFDocument
from pdfminer.pdfinterp import PDFPageInterpreter, PDFResourceManager, resolve1
from pdfminer.pdfpage import PDFPage
from pdfminer.pdfparser import PDFParser
from pdfminer.pdftypes import LITERALS_DCT_DECODE, LITERALS_FLATE_DECODE
from pdfplumber import open as pdf_open

from rag.custom_config_cmd import parse_config
from rag.table_parsing import extract_page_tables_with_bboxes

Num = Union[int, float]
Block = Tuple[int, Num, Num, Num, Num]


# ---------------------------------------------------------------------------
# PDF page/image utilities
# ---------------------------------------------------------------------------

def extract_pages_from_bytes(
    bytes_stream: bytes,
    password: str = "",
    page_numbers: Optional[Container[int]] = None,
    maxpages: int = 0,
    caching: bool = True,
    laparams: Optional[LAParams] = None,
) -> Iterator[LTPage]:
    if laparams is None:
        laparams = LAParams()
    try:
        fp = BytesIO(bytes_stream)
        resource_manager = PDFResourceManager(caching=caching)
        device = PDFPageAggregator(resource_manager, laparams=laparams)
        interpreter = PDFPageInterpreter(resource_manager, device)
        for page in PDFPage.get_pages(
            fp, page_numbers, maxpages=maxpages, password=password, caching=caching
        ):
            interpreter.process_page(page)
            layout = device.get_result()
            yield layout
    except Exception as e:
        logging.exception("Error while streaming pdf")
        logging.exception(str(e))


def get_pdf_number_of_pages(url) -> int:
    file = open(url, "rb") if isinstance(url, str) else BytesIO(url)
    parser = PDFParser(file)
    document = PDFDocument(parser)
    return resolve1(document.catalog["Pages"])["Count"]


def get_pdf_file(url):
    return open(url, "rb") if isinstance(url, str) else BytesIO(url)


def render_pdf_selected_pages(
    pdf_path,
    wannable_pages: Sequence[int] | None = None,
    *,
    resolution: int = 72,
    annotate: bool = False,
    ignore_out_of_range: bool = False,
    unique: bool = True,
) -> List[Image.Image]:
    if resolution <= 0:
        raise ValueError("resolution must be > 0")

    stream: BinaryIO | str
    close_stream = False
    if isinstance(pdf_path, str):
        stream = str(pdf_path)
    elif isinstance(pdf_path, bytes):
        stream = BytesIO(pdf_path)
        close_stream = True
    else:
        if not (hasattr(pdf_path, "read") and hasattr(pdf_path, "seek")):
            raise RuntimeError("Object has no read/seek — cannot open as PDF.")
        stream = pdf_path

    def _unique_keep_order(seq: Iterable[int]) -> List[int]:
        seen: set[int] = set()
        out: List[int] = []
        for x in seq:
            if x not in seen:
                seen.add(x)
                out.append(x)
        return out

    images: List[Image.Image] = []
    try:
        with pdf_open(stream) as pdf:
            total = len(pdf.pages)
            if not wannable_pages:
                page_indices = list(range(total))
            else:
                page_indices = list(wannable_pages)
                if unique:
                    page_indices = _unique_keep_order(page_indices)
                bad = [i for i in page_indices if i < 0 or i >= total]
                if bad and not ignore_out_of_range:
                    raise ValueError(f"Invalid page indices: {bad} (document has {total} pages)")
                if bad and ignore_out_of_range:
                    page_indices = [i for i in page_indices if 0 <= i < total]

            for i in page_indices:
                page = pdf.pages[i]
                page_image = page.to_image(resolution=resolution)
                pil_img = page_image.annotated if annotate else page_image.original
                images.append(pil_img)
    finally:
        if close_stream:
            stream.close()

    return images


# ---------------------------------------------------------------------------
# Text classification helpers (Russian-specific)
# ---------------------------------------------------------------------------

def is_4th_list_indent(text_box: LTTextBox) -> bool:
    text = text_box.get_text().strip()
    return bool(re.match(r"^\d\.\d\.\d\.\d\b", text))


def has_list_like_point(text_box: LTTextBox) -> bool:
    list_starters = ["■", "○", "●"]
    text = text_box.get_text().strip()
    return any(s in text for s in list_starters)


def text_is_bold(text_box: LTTextBox, bold_ratio: float = 0.8) -> bool:
    characters_n = 0
    bold_characters = 0
    for text_line in text_box:
        if not isinstance(text_line, LTTextLine):
            continue
        for char_elem in text_line:
            if not isinstance(char_elem, LTChar):
                continue
            characters_n += 1
            if "bold" in str(char_elem.fontname).lower():
                bold_characters += 1
    if characters_n == 0:
        return False
    return bold_characters / characters_n >= bold_ratio


def is_an_example(text_box: LTTextBox) -> bool:
    example_list = ["пример", "примеры", "примечание", "примечания", "внимание", "внимание!"]
    text = text_box.get_text().strip().lower()
    return text in example_list


# ---------------------------------------------------------------------------
# Layout element wrappers
# ---------------------------------------------------------------------------

class LTCustomTable:
    def __init__(self, bbox, table, page_height: float | int):
        page_height = float(page_height)
        self.bbox = bbox
        self.table = table
        if self.bbox[0] == -1:
            return
        bbox_list = list(self.bbox)
        bbox_list[1], bbox_list[3] = page_height - bbox_list[3], page_height - bbox_list[1]
        self.bbox = tuple(bbox_list)


def out_of_page_boundary(element, lb: int = 820, ub: int = 26) -> bool:
    if not hasattr(element, "bbox"):
        return True
    y = element.bbox[3]
    lower_check = (y <= lb) if lb != -1 else False
    upper_check = (y >= ub) if ub != -1 else False
    return lower_check or upper_check


def out_of_page_by_regex(text: str, pattern) -> bool:
    if not pattern:
        return False
    return bool(pattern.fullmatch(text or ""))


# ---------------------------------------------------------------------------
# Image extraction from pdfminer LTImage
# ---------------------------------------------------------------------------

def short_hash_md5(input_string: str) -> str:
    md5_hash = hashlib.md5()
    md5_hash.update(input_string.encode("utf-8"))
    return md5_hash.hexdigest()


def create_image_name(doc_name, page_number, element_ind, sub_element_ind, img_id) -> str:
    name = f"{doc_name}_P{page_number:03}_E{element_ind:03}_SE{sub_element_ind:02}_N{img_id:02}"
    return short_hash_md5(name)


def is_black_image(pil_img: Image.Image, threshold: int = 5) -> bool:
    arr = np.array(pil_img.convert("L"))
    return bool(arr.max() <= threshold)


def LT_get_bytes(image: LTImage) -> Image.Image:
    width, height = image.srcsize
    channels = len(image.stream.get_data()) / width / height / (image.bits / 8)
    mode: Literal["1", "L", "RGB", "CMYK"]
    if image.bits == 1:
        mode = "1"
    elif image.bits == 8 and channels == 1:
        mode = "L"
    elif image.bits == 8 and channels == 3:
        mode = "RGB"
    elif image.bits == 8 and channels == 4:
        mode = "CMYK"
    else:
        mode = "RGB"
    img = Image.frombytes(mode, image.srcsize, image.stream.get_data(), "raw")
    if mode == "L":
        img = ImageOps.invert(img)
    return img


def LT_get_jpeg(image: LTImage) -> Image.Image:
    raw_data = image.stream.get_rawdata()
    assert raw_data is not None
    if LITERAL_DEVICE_CMYK in image.colorspace:
        ifp = BytesIO(raw_data)
        i = Image.open(ifp)
        i = ImageChops.invert(i)
        i = i.convert("RGB")
        return i
    else:
        ifp = BytesIO(raw_data)
        return Image.open(ifp)


def convert_LTImage_to_PIL(image: LTImage) -> Image.Image:
    filters = image.stream.get_filters()
    if len(filters) == 1 and filters[0][0] in LITERALS_DCT_DECODE:
        return LT_get_jpeg(image)
    elif len(filters) == 1 and filters[0][0] in LITERALS_FLATE_DECODE:
        return LT_get_bytes(image)
    else:
        raise ValueError(f"Image file type not supported. Filters: {filters}")


# ---------------------------------------------------------------------------
# Page layout analysis
# ---------------------------------------------------------------------------

def parse_page_layout(
    doc_name,
    page_layout,
    page_number: int,
    current_tables,
    file,
    lower_boundary: float = 55,
    upper_boundary: float = 808,
    colonne_cuts: list | None = None,
) -> list[dict]:
    elements = []
    image_number = 0

    page_bbox = page_layout.bbox
    page_height = page_bbox[3] - page_bbox[1]

    lb = int(page_height / 100 * lower_boundary)
    ub = int(page_height / 100 * (100 - upper_boundary))

    for element_ind, element in enumerate(page_layout):
        in_table_flag = False
        for df in current_tables:
            table_y1, table_y2 = page_height - df.bbox[3], page_height - df.bbox[1]
            element_y = element.bbox[3]
            if table_y1 <= element_y <= table_y2:
                in_table_flag = True
                break
        if in_table_flag:
            continue
        if isinstance(element, LTTextContainer):
            elements.append(element)
        if isinstance(element, LTFigure):
            elements.append(element)

    for df in current_tables:
        elements.append(LTCustomTable(df.bbox, df.to_pandas(), page_height))

    s_elements = sorted(elements, key=lambda x: x.bbox[3], reverse=True)
    json_elements: list[dict] = []

    for element in s_elements:
        if out_of_page_boundary(element, lb, ub):
            continue

        if isinstance(element, LTTextContainer):
            current_text = element.get_text().strip()
            if len(current_text) <= 3:
                continue
            if colonne_cuts and any(out_of_page_by_regex(current_text, pat) for pat in colonne_cuts):
                logging.info("__regex_out_page_dropped: %r", current_text)
                continue

            element_is_bold = text_is_bold(element)
            element_is_4th_list_indent = is_4th_list_indent(element)
            element_is_header = element_is_bold or element_is_4th_list_indent
            element_is_header = element_is_header and (not has_list_like_point(element))
            element_is_header = element_is_header and (not is_an_example(element))

            el_bbox = [int(v) for v in element.bbox]
            position_int = [
                page_number,
                el_bbox[0],
                el_bbox[2],
                int(page_height) - el_bbox[3],
                int(page_height) - el_bbox[1],
            ]
            json_elements.append({
                "type": "text",
                "content": current_text,
                "is_header": element_is_header,
                "page_number": page_number,
                "position_int": position_int,
            })

        elif isinstance(element, LTFigure):
            for sub_element_ind, sub_element in enumerate(element):
                if not isinstance(sub_element, LTImage):
                    continue
                image_full_name = create_image_name(
                    doc_name, page_number, element_ind, sub_element_ind, image_number
                )
                try:
                    pil_image = convert_LTImage_to_PIL(sub_element)
                except Exception:
                    logging.warning("Failed to convert LTImage to PIL, skipping")
                    continue

                el_bbox = [int(v) for v in element.bbox]
                position_int = [
                    page_number,
                    el_bbox[0],
                    el_bbox[2],
                    int(page_height) - el_bbox[3],
                    int(page_height) - el_bbox[1],
                ]
                image_number += 1
                json_elements.append({
                    "type": "image",
                    "content": f'<image "{image_full_name}">',
                    "is_header": False,
                    "page_number": page_number,
                    "position_int": position_int,
                    "image_guid": image_full_name,
                    "pil_img": pil_image,
                })

        elif isinstance(element, LTCustomTable):
            el_bbox = [int(v) for v in element.bbox]
            position_int = [
                page_number,
                el_bbox[0],
                el_bbox[2],
                int(page_height) - el_bbox[3],
                int(page_height) - el_bbox[1],
            ]
            json_elements.append({
                "type": "text",
                "content": f"\n<TABLE>\n{element.table.to_csv()}\n</TABLE>\n",
                "is_header": False,
                "page_number": page_number,
                "position_int": position_int,
            })

    return json_elements


# ---------------------------------------------------------------------------
# Chunking helpers
# ---------------------------------------------------------------------------

def refine_parsed_text(text: str) -> str:
    return text


def split_by_headers(items, header_key: str = "is_header", min_chars: int = 0, text_key: str = "content"):
    groups: list[list] = []
    current = None
    leading: list = []

    for obj in items:
        if obj.get(header_key):
            if current is not None:
                groups.append(current)
            current = [obj]
            if leading:
                current = leading + current
                leading = []
        else:
            if current is None:
                leading.append(obj)
            else:
                current.append(obj)

    if current is not None:
        groups.append(current)
    elif leading:
        groups.append(leading)

    if min_chars and min_chars > 0 and len(groups) > 1:
        def chunk_len(chunk):
            return sum(len(str(it.get(text_key, ""))) for it in chunk)

        merged = []
        i = 0
        while i < len(groups):
            group = list(groups[i])
            curr_len = chunk_len(group)
            while curr_len < min_chars and (i + 1) < len(groups):
                nxt = groups[i + 1]
                group.extend(nxt)
                curr_len += chunk_len(nxt)
                i += 1
            merged.append(group)
            i += 1
        groups = merged

    return groups


# ---------------------------------------------------------------------------
# Image mosaicking
# ---------------------------------------------------------------------------

def extract_vertical_mosaic(
    pdf_images: Sequence[Image.Image],
    position_int: Sequence[Block],
    zoom_factor: Num = 1.0,
) -> Image.Image:
    if not position_int:
        raise ValueError("position_int is empty — nothing to extract.")
    if zoom_factor <= 0:
        raise ValueError("zoom_factor must be > 0")

    pages_in_blocks = [b[0] for b in position_int]
    first_page = pages_in_blocks[0]
    last_page = pages_in_blocks[-1]

    def crop_page_full_width(page_img: Image.Image, y0: Num, y1: Num) -> Image.Image:
        Y0 = int(round(y0 * zoom_factor))
        Y1 = int(round(y1 * zoom_factor))
        height = page_img.height
        if Y0 < 0:
            Y0 = 0
        if Y1 > height:
            Y1 = height
        if Y0 >= Y1:
            Y1 = min(Y0 + 1, height)
        return page_img.crop((0, Y0, page_img.width, Y1))

    blocks_by_page: dict[int, List[Block]] = {}
    for blk in position_int:
        p = blk[0]
        blocks_by_page.setdefault(p, []).append(blk)

    for p in blocks_by_page.keys():
        idx = p - 1
        if idx < 0 or idx >= len(pdf_images):
            raise ValueError(f"Page number {p} out of range for pdf_images (len={len(pdf_images)}).")

    fragments: List[Image.Image] = []

    if first_page == last_page:
        page_blocks = blocks_by_page[first_page]
        y0_min = min(b[3] for b in page_blocks)
        y1_max = max(b[4] for b in page_blocks)
        page_img = pdf_images[first_page - 1]
        return crop_page_full_width(page_img, y0_min, y1_max)

    first_page_blocks = blocks_by_page[first_page]
    first_y0 = min(b[3] for b in first_page_blocks)
    first_y1 = max(b[4] for b in first_page_blocks)
    first_img = pdf_images[first_page - 1]
    fragments.append(crop_page_full_width(first_img, first_y0, first_y1))

    for p in range(first_page + 1, last_page):
        page_img = pdf_images[p - 1]
        fragments.append(page_img)

    last_page_blocks = blocks_by_page[last_page]
    last_y0 = min(b[3] for b in last_page_blocks)
    last_y1 = max(b[4] for b in last_page_blocks)
    last_img = pdf_images[last_page - 1]
    fragments.append(crop_page_full_width(last_img, last_y0, last_y1))

    total_width = max(img.width for img in fragments)
    total_height = sum(img.height for img in fragments)
    base_mode = fragments[0].mode
    normed = [(img if img.mode == base_mode else img.convert(base_mode)) for img in fragments]
    mosaic = Image.new(base_mode, (total_width, total_height))
    y_cursor = 0
    for part in normed:
        mosaic.paste(part, (0, y_cursor))
        y_cursor += part.height
    return mosaic


# ---------------------------------------------------------------------------
# Chunk assembly
# ---------------------------------------------------------------------------

def join_pdf_data(pdf_data, doc_name, pdf_images, zoom_factor, chunk_token_num: int = 0):
    output_data = []
    grouped_data = split_by_headers(pdf_data, min_chars=chunk_token_num)

    for group in grouped_data:
        if not group:
            continue

        el_dict = {}
        el_dict["docnm_kwd"] = doc_name

        title = group[0]["content"][:16]
        el_dict["title_tks"] = title
        el_dict["title_sm_tks"] = title.lower()
        el_dict["page_num_int"] = [element["page_number"] for element in group]
        el_dict["position_int"] = [element["position_int"] for element in group]
        el_dict["top_int"] = [element["position_int"][3] for element in group]
        el_dict["content_with_weight"] = "\n".join([element["content"] for element in group])
        el_dict["content_ltks"] = " ".join([refine_parsed_text(element["content"]) for element in group])
        el_dict["content_sm_ltks"] = " ".join([refine_parsed_text(element["content"]) for element in group])

        try:
            mosaic = extract_vertical_mosaic(
                pdf_images,
                [tuple(el_block) for el_block in el_dict["position_int"]],
                zoom_factor,
            )
            el_dict["image"] = mosaic
        except Exception as e:
            logging.warning(f"Failed to create mosaic: {e}")
            el_dict["image"] = None

        inline_images = [el["pil_img"] for el in group if el.get("type") == "image"]
        inline_images_ids = [el["image_guid"] for el in group if el.get("type") == "image"]
        el_dict["inline_images"] = inline_images
        el_dict["inline_images_ids"] = inline_images_ids

        output_data.append(el_dict)

    return output_data


# ---------------------------------------------------------------------------
# Main pipeline: pdfminer layout-based parsing
# ---------------------------------------------------------------------------

def parse_pdf_pages(pdf_path, doc_name, zoom_factor, from_page, to_page, parser_config):
    additional_info = parser_config.get("additional_parsing_info", "")
    logging.info(f"__parser_config_ParsingInfo: '{parser_config}'")
    logging.info(f"__parser_config_additionalParsingInfo: '{additional_info}'")

    try:
        additional_info = parse_config(additional_info)
    except Exception as e:
        logging.error("Error while getting parsing args")
        raise e

    logging.info(f"__parser_config_parsed info: '{additional_info}'")

    colonne_cuts = [re.compile(c_cut) for c_cut in additional_info["cut_colonne"]]

    total_pages = get_pdf_number_of_pages(pdf_path)
    logging.info(f"__chunk__found_{total_pages} pages")

    start_index = max(0, from_page if from_page is not None else 0)
    end_index = min(total_pages - 1, to_page if to_page is not None else total_pages - 1)

    wannable_pages = list(range(start_index, end_index + 1)) if start_index <= end_index else []
    logging.info(f"__chunk__page_interval from {start_index + 1} to {end_index + 1}")

    pdf_data: list[dict] = []
    file = get_pdf_file(pdf_path)
    pdf_images = render_pdf_selected_pages(pdf_path, resolution=72 * zoom_factor)

    if isinstance(pdf_path, str):
        extracted_pages = extract_pages(pdf_path, page_numbers=wannable_pages)
    else:
        extracted_pages = extract_pages_from_bytes(pdf_path, page_numbers=wannable_pages)

    for page_ind, page_layout in enumerate(extracted_pages):
        actual_page_number = wannable_pages[page_ind]

        tables = extract_page_tables_with_bboxes(pdf_path, actual_page_number)

        page_data = parse_page_layout(
            doc_name,
            page_layout,
            actual_page_number + 1,
            tables,
            file,
            lower_boundary=additional_info["lower_boundary"],
            upper_boundary=additional_info["upper_boundary"],
            colonne_cuts=colonne_cuts,
        )
        pdf_data += page_data

    pdf_data = join_pdf_data(
        pdf_data,
        doc_name,
        pdf_images,
        zoom_factor,
        parser_config.get("chunk_token_num", 128),
    )
    return pdf_data


# ---------------------------------------------------------------------------
# Main pipeline: vision-based LLM parsing (parallel via trio)
# ---------------------------------------------------------------------------

def parse_pdf_as_images(pdf_path, doc_name, zoom_factor, from_page, to_page, parser_config, tenant_id):
    from api.db import LLMType
    from api.db.services.llm_service import LLMBundle

    additional_info = parser_config.get("additional_parsing_info", "")
    try:
        additional_info = parse_config(additional_info)
    except Exception as e:
        logging.error("Error while getting parsing args")
        raise e

    total_pages = get_pdf_number_of_pages(pdf_path)
    logging.info(f"__chunk__found_{total_pages} pages")

    start_index = max(0, from_page if from_page is not None else 0)
    end_index = min(total_pages - 1, to_page if to_page is not None else total_pages - 1)
    wannable_pages = list(range(start_index, end_index + 1)) if start_index <= end_index else []

    cv_mdl = LLMBundle(tenant_id, LLMType.IMAGE2TEXT, lang="English")

    try:
        cv_mdl.mdl.stop_all_running_models()
    except Exception:
        pass

    pdf_images = render_pdf_selected_pages(pdf_path, resolution=72)

    cv_prompt = """Переведи документ в Markdown формат"""

    def _convert_pdf_image_to_bytes(page_ind: int) -> bytes:
        img = pdf_images[page_ind]
        img_binary = io.BytesIO()
        img.save(img_binary, format="JPEG")
        img_binary.seek(0)
        return img_binary.read()

    def _form_ans_format(page_ind: int, ans: str) -> dict:
        return {
            "is_header": False,
            "content": ans,
            "page_number": page_ind,
            "position_int": [page_ind + 1, 0, 0, 0, 0],
            "type": "text",
        }

    pdf_data: list[dict] = []

    try:
        import trio

        def _process_pages_parallel():
            async def _run():
                pdf_data_local: list[dict] = []
                state_pages = {"done": 0}
                lock_pages = trio.Lock()

                async def process_page(page_ind: int):
                    def _describe_sync():
                        return cv_mdl.describe_with_prompt(
                            _convert_pdf_image_to_bytes(page_ind),
                            cv_prompt,
                        )

                    ans = await trio.to_thread.run_sync(_describe_sync)
                    logging.info(f"__VLLM__{ans}")

                    async with lock_pages:
                        pdf_data_local.append(_form_ans_format(page_ind, ans))
                        state_pages["done"] += 1
                        logging.info(f"VLLM: completed {state_pages['done']}/{len(wannable_pages)}")

                async with trio.open_nursery() as nursery:
                    for page_ind in wannable_pages:
                        nursery.start_soon(process_page, page_ind)

                return pdf_data_local

            return trio.run(_run)

        pdf_data = _process_pages_parallel()

    except ImportError:
        logging.warning("trio not available, falling back to sequential processing")
        for page_ind in wannable_pages:
            ans = cv_mdl.describe_with_prompt(
                _convert_pdf_image_to_bytes(page_ind),
                cv_prompt,
            )
            logging.info(f"__VLLM__{ans}")
            pdf_data.append(_form_ans_format(page_ind, ans))

    pdf_data.sort(key=lambda x: x["page_number"])

    pdf_data = join_pdf_data(
        pdf_data,
        doc_name,
        pdf_images,
        zoom_factor,
        parser_config.get("chunk_token_num", 128),
    )
    return pdf_data
