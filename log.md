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
  - Since the data comes from a pdf some parsing would be required. However, since the pdf is image-based, some OCR would be required to capture all the text.
  - Decided to use an LLM-based OCR since the texts are quite unstructured and has complex layouts (some of them are just paragraphs, some of them has bullet points, and there's also a lot of illustrations too)
  - Instead of letting one strong LLM to read the entire pdf and do all the work to structure it based on a set ontology, it is better to split them into smaller workflows and use smaller model which makes it easier to debug, more cost effective, and less chance of hallucination.
  - The first workflow is to parse the pdf into raw texts. Kept parser as pure OCR without any semantic analysis, just raw extraction. 
  - API call is done page by page to reduce hallucination as part of context management. Uses `claude-haiku` model to keep cost low and since this only acts as parser.
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
- **Problem**: render scale=2.0 seems too low, which makes the model misread characters, like "Ring of Elven Lords" being read as "Ring of Eleven Lords".
- **Fix**: Increased render scale to 3.0 and switched from PNG to JPEG (quality=85) to compress and stay under Anthropic's 5 MB image limit (~700–850 KB per page vs ~5.6 MB as PNG).

### Handling Multi-page item description
- **Problem**: Some items have descriptions more than 1 page, and it was being truncated to only the first page. To ensure continuation, I include the context from the previous page, thus, it has to be run sequentially. The parallel processing implemented before is reverted. 
- **Fix**: Switched to sequential page processing with a `carry` variable holding the last item pending until it determines the next page does not contain any continuation. A `CONTINUATION_HINT` is injected into the prompt containing the item name and last 200 characters of its description as a context, so the model knows exactly where to resume. 


## [2026-05-23 6:35 PM - 11:07 PM] - Brainstorming Ontology Design
- **Action**: Created initial ontology design in `reznar/ontology.py` 
- **Thought Process**:
  - Most of the time was spent exploring the data and seeking for common grounds across all items. Like mentioned, every item has its own unique and can basically do anything. Thus, focusing on the main goal finding patterns to help Reznar guide his customers is the best way to go.
  - To start of simple, I used the guide to build an ontology that wrap around  offensive and defensive improvements, creatures it is effective or resistant against, and environment it is strong at.
  - There are definitely still room for improvement here in terms of the entites hierarchical structure and details it has. But for now, it seems pretty solid.



## [2026-05-24 11:22 AM – 1:23 PM] - Ontology Redesign & Simplification
- **Action**: Redesigned `reznar/ontology.py` and replaced per-form class hierarchy with a single `Item` carrying optional components (`Offense`, `Defense`, `Environment`, `Limitations`).
- **Action**: Simplified the schema by dropping `WeaponType`, `ArmorType`, `DamageType`, `Recharge` enums and all their dependencies, cleaned up normalizers and removed hard-coded synonyms.
- **Thought Process**:
  - Having scalability in mind, the initial ontology seems to be lacking. For example, what if there's a new item like a Ring that can deal damage? The current ontology would not be able to handle that since Ring only has defense component attached to it. That said, splitting by item form seems like not the way to go.
  - With the core variables and features already defined, I just need to restructure them in a way that is more flexible and modular. In this case, letting one class handle multiple forms seem to be the right move since all item can have offensive/defensive improvements, effectiveness towards creatures and in certain environment, and limitations. Splitting and grouping these variables into its own dimension, like Offensive, Defensive, Environment, and Limitations, creates modularity and flexibility we need.
  - This schema able to handle all combinations that an item might have. For example, if there's a new potion that can deal damage and effective in water, or a new armor that is effective in forest only. Furthermore, adding more features to the dimensions are also much easier. For example, if I want to handle a new feature that gives an item disadvantage in certain environment, I can easily add that to the Environment class.
  - Another thing that I considered is the complexity and how much detail I want to include in the ontology. Focusing on what Reznar wants, there's a lot of details that does not contribute to his goals. For example, the weapon type (sword/mace/axe/etc), armor type (leather/plate/etc), and so on, are not that important. Reznar wants something that help him filter based on offensive/defensive improvements, effectiveness in environment and towards creatures, limitations, and where the item is being used. Weapon type and armor type does not seem to be exactly helpful in doing so, thus, removed. 


## [2026-05-24 2:25 PM – 3:03 PM] - Slot & Form Redesign
- **Action**: Redesign how `Slot` and `Form` are being handled in `reznar/ontology.py`. Both `Slot` and `Form` are now extracted directly using LLM instead of letting slot derived from `Form` using static `FORM_SLOT` mapping.
- **Action**: Removed `FORM_SLOT` mapping entirely. Added `other` value to handle edge cases to `Form` and `Condition` enums. Merged `hands` and `hand` into a single `hand` slot.
- **Thought Process**:
  - Reznar mentioned that it is crucial to distinguish where the item is going to be worn. With the current design, which relies on the form classification, is prone to breaking. The form could be misclassified or does not exist (in case new item comes along) and the mapping for the slot is not robust enough. Thus letting the LLM to decide this along based on the description context would be a better option.
  - The enums for `Form` and `Condition` are prone to change if new item comes along, thus, to handle this edge case, I created a new value `other` for both enums.


## [2026-05-24 3:14 PM – 6:03 PM] - Created Extraction Pipeline + Refine Ontology
- **Action**: Created and ran `reznar/extract.py` which reads `items_raw.json`, invokes LLM call per item using the Ontology design, and insert them to Postgres table.
- **Action**: Refine prompt and normalization functions in `reznar/ontology.py` for more consistent results.
- **Action**: Added `DamageTypeList` in `reznar/ontology.py` to capture what type of damage it is resistant towards or what type of damage it gives, depending whether it is a defensive or offensive component.
- **Thought Process**:
  - From the initial run, it seems like creature types and environment types is still messy. The LLM output is quite inconsistent in terms of the naming it has decided on, despite after a couple of iterations refining the prompt. For more structured output, I think using enums with "other" to handle edge cases would be better. This way, we have much more structured output, and types that is not captured can easily be added to the enums later on. Hence, we still have the scalability and structured output we are looking for. 


## [2026-05-24 6:36 PM – 7:03 PM] - Enum Constraints for Creature, Damage Type, and Environment Fields
- **Action**: Added `CreatureFamily`, `DamageType`, and `EnvironmentType` enums to `reznar/ontology.py`, replacing the free-string `list[str]` fields for `effective_against`, `resistances_against`, `damage_resistances`, and `strong_in`.
- **Action**: Removed normalization functions and other helper functions.
- **Action**: Re-ran `reznar/extract.py` for quality check.
- **Thought Process**:
  - LLM could output anything in any format and any names, which makes it very difficult to handle all cases. For example, it may classify a human as "humanoid", or simply "human", or "humans", or "living_being", or even all of them in different items. It is much easier to handle all cases for types, in this case, creature types.
  - On the other hand, we will also get a more structured output that make filtering much more easier and consistent.