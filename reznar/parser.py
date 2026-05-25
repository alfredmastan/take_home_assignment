"""Stage 1: PDF → data/items_raw.json using Claude vision (OCR + light structure)."""

from __future__ import annotations

import base64
import io
import json
from pathlib import Path
from typing import Annotated

import pypdfium2
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, BeforeValidator

from reznar.config import VISION_MODEL

PDF_PATH = Path("data/items_combined.pdf")
OUTPUT_PATH = Path("data/items_raw.json")

PROMPT = (
    "You are OCR-ing a page from Reznar's Arcane Oddities, a fantasy magic item shop catalog. "
    "Each item follows this text structure:\n"
    "  1. Item name — rendered in bold or ALL-CAPS, 1–5 words, standalone line, no trailing punctuation\n"
    "  2. Item type line — the very next text line, e.g. 'Armor (plate), rare (requires attunement)'. "
    "Always contains a type keyword (wondrous item, armor, weapon, ring, staff, potion, scroll, etc.) "
    "and a rarity word (common, uncommon, rare, very rare, legendary, artifact).\n"
    "  3. Description — every paragraph after the type line\n\n"
    "IMPORTANT — illustrations: decorative illustrations appear anywhere on the page (top, side, "
    "bottom). Their position is purely decorative and carries NO structural meaning. "
    "Ignore image placement entirely when deciding where items begin or end.\n\n"
    "For each item extract:\n"
    "  name        – the item's name (from the bold/ALL-CAPS heading)\n"
    "  item_type   – from the type line immediately after the name, e.g. 'weapon', 'armor (plate)', "
    "'wondrous item', 'ring', 'staff', 'potion', 'scroll', etc.\n"
    "  rarity      – exactly one of: common, uncommon, rare, very rare, legendary, artifact\n"
    "  attunement  – true if the type line says 'requires attunement', false otherwise\n"
    "  description – verbatim text starting from the SECOND paragraph after the item name "
    "(i.e. everything after the type line). Do NOT include the type line in description.\n\n"
    "If the page contains no magic items (cover, table of contents, blank page, etc.) "
    "return an empty items list with first_item_is_continuation=false."
)

CONTINUATION_HINT = (
    '\n\nCONTEXT: The previous page ended partway through an item named "{name}". '
    "The last text extracted from that item was:\n"
    "  ...{tail}\n\n"
    "Use this three-step algorithm to decide whether this page continues that item:\n\n"
    "  STEP 1 — Discard all images. Illustrations are decorative; their position on the page "
    "tells you nothing about item boundaries. Do not factor image placement into this decision.\n\n"
    "  STEP 2 — Scan the TEXT on this page from top to bottom and locate the first text block.\n\n"
    "  STEP 3 — Classify that first text block:\n"
    "    • If it is an ALL-CAPS or bold short phrase (1–5 words, no trailing punctuation) → "
    "it is a NEW item name. Set first_item_is_continuation=false.\n"
    "    • If it is plain body/paragraph prose (not a bold/ALL-CAPS heading) → it is a "
    'continuation of "{name}". Set first_item_is_continuation=true and transcribe ALL text '
    "on this page that belongs to that item; do not skip any paragraphs.\n\n"
    "CRITICAL RULE: An ALL-CAPS or bold short phrase is ALWAYS a new item name. "
    'Never absorb it into "{name}"\'s description regardless of surrounding images or layout.'
)


class RawItem(BaseModel):
    name: str
    item_type: str
    rarity: str
    attunement: bool
    description: str


def _coerce_items(v: object) -> object:
    if isinstance(v, str):
        return json.loads(v)
    return v


class PageItems(BaseModel):
    first_item_is_continuation: bool = False
    items: Annotated[list[RawItem], BeforeValidator(_coerce_items)]


def _page_to_jpeg_bytes(page: pypdfium2.PdfPage, scale: float = 3.0) -> bytes:
    bitmap = page.render(scale=scale)
    pil_image = bitmap.to_pil()
    buf = io.BytesIO()
    pil_image.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def _extract_page(llm_structured, image_bytes: bytes, prev_item: dict | None = None) -> PageItems:
    b64 = base64.standard_b64encode(image_bytes).decode()
    prompt = PROMPT
    if prev_item:
        tail = prev_item["description"][-200:].replace("\n", " ").strip()
        prompt += CONTINUATION_HINT.format(name=prev_item["name"], tail=tail)
    message = HumanMessage(
        content=[
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
            {"type": "text", "text": prompt},
        ]
    )
    return llm_structured.invoke([message])


def main() -> None:
    llm = ChatAnthropic(model=VISION_MODEL)
    llm_structured = llm.with_structured_output(PageItems)

    doc = pypdfium2.PdfDocument(str(PDF_PATH))
    n_pages = len(doc)
    all_items: list[dict] = []
    carry: dict | None = None  # last item from previous page, not yet emitted

    for i, page in enumerate(doc):
        try:
            image_bytes = _page_to_jpeg_bytes(page)
            page_result = _extract_page(
                llm_structured, image_bytes, prev_item=carry
            )  # give the LLM the last item from the previous page, if any, so it can decide whether this page continues it
        except Exception as exc:
            print(f"Page {i + 1} ERROR: {exc}")
            continue

        items = [item.model_dump() for item in page_result.items]

        if page_result.first_item_is_continuation and carry is not None:
            carry["description"] += "\n" + items[0]["description"]
            items = items[1:]

        if items:
            if carry is not None:
                all_items.append(carry)
            all_items.extend(
                items[:-1]
            )  # grab all but the last item, which may be continued on the next page
            carry = items[-1]  # store the last item for potential continuation on the next page

        cont = " (continuation)" if page_result.first_item_is_continuation else ""
        print(f"Page {i + 1}/{n_pages}: {len(page_result.items)} item(s){cont}")

    if carry is not None:
        all_items.append(carry)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(all_items, indent=2))
    print(f"\nWrote {len(all_items)} items → {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
