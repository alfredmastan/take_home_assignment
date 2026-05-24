# Project Log

## [2026-05-23 09:30 AM – 10:00 AM] - Repository Fork & Initial Setup
- **Action**: Forked and cloned the official GitHub repository to the local machine.
- **Action**: Configured the local development environment and initialized the database.
- **Thought Process**: Verified the database connection immediately after setup to ensure the baseline infrastructure is stable before writing any code.
- **Next Steps**: Review the project architecture and plan the first incremental feature implementation.

## [2026-05-23 10:00 AM – 11:35 AM] - Ontology Architecture Brainstorming
- **Action**: Began brainstorming the right architecture and efficiency approach for `reznar/ontology.py`.
- **Thought Process**: Here I'm just exploring on what would be the best model design and capture client's goals to represent rarity tiers, attunement, equipment slots, pattern dimensions, etc, for the extraction pipeline.


## [2026-05-23 11:35 AM – 1:53 PM] - Created Initial PDF parser
- **Action**: Created `reznar/config.py` to load model names (`VISION_MODEL`, `ANALYSIS_MODEL`) from `.env`, decoupling model selection from pipeline code.
- **Action**: Added pipeline dependencies to `pyproject.toml` (`langchain`, `langchain-anthropic`, `pypdfium2`, `pillow`, `python-dotenv`) and ran `uv sync`.
- **Action**: Created `reznar/parse_pdf.py` — renders each PDF page to a base64 PNG via `pypdfium2` (scale=2) and sends it to the vision model via LangChain's `ChatAnthropic` to extract items with verbatim descriptions.
- **Action**: Successfully ran parser and generated `data/items_raw.json` with structured item records (fields: `name`, `item_type`, `rarity`, `attunement`, `description`).
- **Thought Process**: 
  - Kept parser as pure OCR without any semantic analysis, just raw extraction. An LLM-based OCR is used here since the pdf is image based and has complex layouts (some of them are paragraphs and some of them has bullet points)
  - API call is done page by page to reduce hallucination in terms of context management. Uses `claude-haiku` model to keep cost low and since this only acts as parser.
  - Uses LangChain as an additional abstract layer to make it easier to swap models.
  - JSON format is used to separate each item and enable  
- **Next Steps**: Design `reznar/ontology.py` Pydantic models, then build `reznar/extract.py` which further break down each item descriptions from the extracted json.

## [2026-05-23 2:24 PM - 2:40 PM] - Parallelized PDF Parser
- **Action**: Refactored `reznar/parse_pdf.py` to process pages concurrently using `ThreadPoolExecutor(max_workers=5)` instead of sequentially.
- **Thought Process**:
  - Each page's API call is fully independent, thus we can parallelize it for faster parsing.
  - `MAX_WORKERS=5` is used in respect to Haiku's rate limits. But we can change this up accordingly.

## [2026-05-23 2:47 PM - 6:00 PM] - OCR Quality & Multi-page Item Description Handling
Noticed 2 problems in the parsed JSON. Some of the texts are misspelled and item descriptions are being cut off. Detailed key problem and action taken explained below:

### OCR quality
- **Problem**: render scale=2.0 is too low, which makes the model misread characters, like "Ring of Elven Lords" being read as "Ring of Eleven Lords".
- **Fix**: Increased render scale to 3.0 and switched from PNG to JPEG (quality=85) to stay under Anthropic's 5 MB image limit (~700–850 KB per page vs ~5.6 MB as PNG).

### Handling Multi-page item description
- **Problem**: Some items have descriptions more than 1 page, and it was being truncated to only the first page. To ensure continuation, I include the context from the previous page, thus, it must be run sequentially. The parallel processing implemented before is reverted. 
- **Fix**: Switched to sequential page processing with a `carry` variable holding the last item pending until it determines the next page does not contain any continuation. A `CONTINUATION_HINT` is injected into the prompt containing the item name and last 200 characters of its description as a context, so the model knows exactly where to resume. 


