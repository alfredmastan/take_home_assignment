"""Stage 1: PDF → data/items_raw.json using Claude vision (OCR + light structure)."""

from __future__ import annotations

import base64
import io
import json
from pathlib import Path

import pypdfium2
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage
from pydantic import BaseModel

from reznar.config import VISION_MODEL

PDF_PATH = Path("data/items_combined.pdf")
OUTPUT_PATH = Path("data/items_raw.json")

PROMPT = (
    "You are OCR-ing a page from Reznar's Arcane Oddities, a fantasy magic item shop catalog. "
    "Extract every magic item that appears on this page.\n\n"
    "For each item return:\n"
    "  name        – the item's name\n"
    "  item_type   – e.g. weapon, armor, wondrous item, ring, staff, potion, scroll, etc.\n"
    "  rarity      – exactly one of: common, uncommon, rare, very rare, legendary, artifact\n"
    "  attunement  – true if the text says 'requires attunement', false otherwise\n"
    "  description – the full description text verbatim from the page\n\n"
    "If the page contains no magic items (cover, table of contents, blank page, etc.) "
    "return an empty items list."
)


class RawItem(BaseModel):
    name: str
    item_type: str
    rarity: str
    attunement: bool
    description: str


class PageItems(BaseModel):
    items: list[RawItem]


def _page_to_png_bytes(page: pypdfium2.PdfPage, scale: float = 2.0) -> bytes:
    bitmap = page.render(scale=scale)
    pil_image = bitmap.to_pil()
    buf = io.BytesIO()
    pil_image.save(buf, format="PNG")
    return buf.getvalue()


def _extract_page(llm_structured, image_bytes: bytes) -> list[dict]:
    b64 = base64.standard_b64encode(image_bytes).decode()
    message = HumanMessage(
        content=[
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
            {"type": "text", "text": PROMPT},
        ]
    )
    result: PageItems = llm_structured.invoke([message])
    return [item.model_dump() for item in result.items]


def main() -> None:
    llm = ChatAnthropic(model=VISION_MODEL)
    llm_structured = llm.with_structured_output(PageItems)

    doc = pypdfium2.PdfDocument(str(PDF_PATH))
    n_pages = len(doc)
    all_items: list[dict] = []

    for i, page in enumerate(doc):
        print(f"Page {i + 1}/{n_pages} ...", end=" ", flush=True)
        try:
            image_bytes = _page_to_png_bytes(page)
            items = _extract_page(llm_structured, image_bytes)
            print(f"{len(items)} item(s)")
            all_items.extend(items)
        except Exception as exc:
            print(f"ERROR: {exc}")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(all_items, indent=2))
    print(f"\nWrote {len(all_items)} items → {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
