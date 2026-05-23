# Project Log

## [2026-05-23 09:30 AM – 10:00 AM] - Repository Fork & Initial Setup
- **Action**: Forked and cloned the official GitHub repository to the local machine.
- **Action**: Configured the local development environment and initialized the database.
- **Thought Process**: Verified the database connection immediately after setup to ensure the baseline infrastructure is stable before writing any code.
- **Next Steps**: Review the project architecture and plan the first incremental feature implementation.

## [2026-05-23 10:00 AM – 11:35 AM] - Ontology Architecture Brainstorming
- **Action**: Began brainstorming the right architecture and efficiency approach for `reznar/ontology.py`.
- **Thought Process**: Exploring entity model design, field validators, and how to best capture client's goals in terms of represent rarity tiers, attunement, equipment slots, and pattern dimensions for the extraction pipeline.


## [2026-05-23 11:35 AM – 1:53 PM] - Created Initial PDF parser
- **Action**: Created `reznar/config.py` to load model names (`VISION_MODEL`, `ANALYSIS_MODEL`) from `.env`, decoupling model selection from pipeline code.
- **Action**: Added pipeline dependencies to `pyproject.toml` (`langchain`, `langchain-anthropic`, `pypdfium2`, `pillow`, `python-dotenv`) and ran `uv sync`.
- **Action**: Created `reznar/parse_pdf.py` — renders each PDF page to a base64 PNG via `pypdfium2` (scale=2) and sends it to the vision model via LangChain's `ChatAnthropic` to extract items with verbatim descriptions.
- **Action**: Successfully ran parser and generated `data/items_raw.json` with structured item records (fields: `name`, `item_type`, `rarity`, `attunement`, `description`).
- **Thought Process**: 
  - Kept parser as pure OCR without any semantic analysis, just raw extraction. An LLM-based OCR is used here since the pdf is image based and has complex layouts (some of them are paragraphs and some of them has bullet points)
  - API call is done page by page to reduce hallucination in terms of context management. Uses `claude-haiku` model to keep cost low and since this only acts as parser.
  - Uses LangChain as an additional abstract layer to make it easier to swap models.
- **Next Steps**: Design `reznar/ontology.py` Pydantic models, then build `reznar/extract.py` which further break down each items from the descriptions extracted.