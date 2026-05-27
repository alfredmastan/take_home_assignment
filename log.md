# Project Log

## [2026-05-23 09:30 AM – 10:00 AM] - Repository Fork & Initial Setup
- **Action**: Forked and cloned the official GitHub repository to the local machine.
- **Action**: Configured the local development environment and initialized the database.
- **Thought Process**: Verified the database connection immediately after setup to ensure the baseline infrastructure is stable before writing any code.
- **Next Steps**: Review the project architecture and plan the first incremental feature implementation.

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
  - JSON format is used to separate each item and enable per item processing. 
- **Next Steps**: Design `reznar/ontology.py` Pydantic models, then build `reznar/extract.py` which further break down each item descriptions from the extracted json.

## [2026-05-23 2:24 PM - 2:40 PM] - Parallelized PDF Parser
- **Action**: Refactored `reznar/parse_pdf.py` to process pages concurrently using `ThreadPoolExecutor(max_workers=5)` instead of sequentially.
- **Thought Process**:
  - Each page's API call is fully independent, thus we can parallelize it for faster parsing.
  - `MAX_WORKERS=5` is used in respect to Haiku's rate limits. 

## [2026-05-23 2:47 PM - 6:00 PM] - OCR Quality & Multi-page Item Description Handling
Noticed 2 major problems in the parsed JSON after a couple of runs and manually cross checking it. Some of the texts are misspelled and item descriptions are being cut off. Detailed key problem and action taken explained below:

### OCR quality
- **Problem**: render scale=2.0 seems too low, which makes the model misread characters, like "Ring of Elven Lords" being read as "Ring of Eleven Lords".
- **Fix**: Increased render scale to 3.0 and switched from PNG to JPEG (quality=85) to compress and stay under Anthropic's 5 MB image limit (~700–850 KB per page vs ~5.6 MB as PNG).

### Handling Multi-page item description
- **Problem**: Some items have descriptions more than 1 page, and it was being truncated to only the first page. Some of them are missing the first 1-3 paragraphs. 
- **Fix**: Refined the main prompt to be more specific in terms of detecting the text for items.witched to sequential page processing with a `carry` variable holding the last item pending until it determines the next page does not contain any continuation. A `CONTINUATION_HINT` is injected into the prompt containing the item name and last 200 characters of its description as a context, so the model knows exactly where to resume. 


## [2026-05-23 6:35 PM - 11:07 PM] - Created Initial Ontology Design
- **Action**: Created initial ontology design in `reznar/ontology.py` 
- **Thought Process**:
  - Exploring the data and seeking for common grounds across all items. Like mentioned, every item has its own uniqueness and can basically do anything. Thus, focusing on the main goal of finding patterns to help Reznar guide his customers is the best way to go.
  - Intuitively, the items naturally split along the form factor of what it is, whether it is a shield, armor, weapon, etc. This makes it easier to filter something like, "which weapon is good against vampires?" or "what armor works best in water environment?"
  - I also split them further into capabilities, specifically into offense and defense. Each of them consist of fields like, creatures it is well against, damage it resists or inflicts, damage bonus or defense bonus, and etc, which are the key fields for Reznar use case and for rarity prediction later on. This way, each form gets their own capabilities, i.e. weapons get offense, ring gets defense, and armor gets both. 
  - All fields are then handled using enums with normalization layer to ensure proper consistent structure and reduce hallucination from the LLM.
  - Structuring it this way also enable us to have one single flat table in the database, making it much easier and simpler to filter.


## [2026-05-24 11:22 AM – 1:23 PM] - Ontology Redesign & Simplification
- **Action**: Redesigned `reznar/ontology.py` and replaced per-form class hierarchy with a single `Item` carrying optional components (`Offense`, `Defense`, `Environment`, `Limitations`).
- **Action**: Simplified the schema by dropping `WeaponType`, `ArmorType`, `DamageType`, `Recharge` enums and all their dependencies, cleaned up normalizers and removed hard-coded synonyms.
- **Thought Process**:
  - When considering scalability, the initial ontology seems to be lacking flexibility. For example, what if there's a new item like a Ring that can deal damage? The current ontology would not be able to handle that since Ring only has defense component attached to it. That said, splitting by item form seems like not the way to go.
  - With the core variables and features already defined, I just need to restructure them in a way that is more flexible and modular. In this case, letting one class handle multiple forms seem to be the right move since all items can have offensive/defensive improvements, effectiveness towards creatures and in certain environment, and limitations. Splitting and grouping these variables into its own dimension, like Offensive, Defensive, Environment, and Limitations, creates modularity and flexibility we need.
  - This schema is able to handle all combinations that an item might have. For example, if there's a new potion that can deal damage and effective in water, or a new armor that is effective in forest only. Furthermore, adding more features to the dimensions are also much easier. For example, if I want to handle a new feature that gives an item disadvantage in certain environment, I can easily add that to the Environment class.
  - Another thing that I considered is the complexity and how much detail I want to include in the ontology. Focusing on what Reznar wants, there's a lot of details that does not contribute to his goals. For example, the weapon type (sword/mace/axe/etc), armor type (leather/plate/etc), and so on, are not that important. Reznar wants something that help him filter based on offensive/defensive improvements, effectiveness in environment and towards creatures, limitations, and where the item is being used. Weapon type and armor type does not seem to be exactly helpful in doing so, thus, removed. 


## [2026-05-24 2:25 PM – 3:03 PM] - Slot & Form Redesign
- **Action**: Redesign how `Slot` and `Form` are being handled in `reznar/ontology.py`. Both `Slot` and `Form` are now extracted directly using LLM instead of letting slot derived from `Form` using static `FORM_SLOT` mapping.
- **Action**: Removed `FORM_SLOT` mapping entirely. Added `other` value to handle edge cases to `Form` and `Condition` enums. Merged `hands` and `hand` into a single `hand` slot.
- **Thought Process**:
  - Reznar mentioned that it is crucial to distinguish where the item is going to be worn. The current design relies on form classification, which is prone to breaking. The form could be misclassified or might not exist (in case a new item comes along), and the mapping for the slot is not robust enough. Thus letting the LLM to decide this along based on the description context would be a better option.
  - The enums for `Form` and `Condition` are prone to change if new item comes along, thus, to handle this edge case, I created a new value `other` for both enums.


## [2026-05-24 3:14 PM – 6:03 PM] - Created Extraction Pipeline + Refine Ontology
- **Action**: Created and ran `reznar/extract.py` which reads `items_raw.json`, invokes LLM call per item using the Ontology design, and insert them to Postgres table.
- **Action**: Refine prompt and normalization functions in `reznar/ontology.py` for more consistent results.
- **Action**: Added `DamageTypeList` in `reznar/ontology.py` to capture what type of damage it is resistant towards or what type of damage it gives, depending whether it is a defensive or offensive component.
- **Thought Process**:
  - From the initial run, it seems like creature types and environment types are still messy. The LLM outputs are quite inconsistent despite having specific prompts. So, for more structured output, I use enums with "other" to handle edge cases. This way, we have much more structured output, and types that is not captured can easily be added to the enums later on. Hence, we still have the scalability and structured output we are looking for. 


## [2026-05-24 6:36 PM – 7:03 PM] - Added Enum Constraints for Creatures, Damage Type, and Environments
- **Action**: Added `CreatureFamily`, `DamageType`, and `EnvironmentType` enums to `reznar/ontology.py`, replacing the free-string `list[str]` fields for `effective_against`, `resistances_against`, `damage_resistances`, and `strong_in`.
- **Action**: Removed normalization functions and other helper functions.
- **Action**: Re-ran `reznar/extract.py` for quality check.
- **Thought Process**:
  - After a couple of runs, I noticed that letting creatures, damage type, and environment as free form types causes major inconsistency. For example, it may classify a human as "humanoid", or simply "human", or "humans", or "living_being", or even all of them in different items. Thus, I created more enums for them with "other" to get a more structured output and be able to handle edge cases. It also makes filtering much easier and more consistent.

## [2026-05-24 9:13 PM] - Added Run Instructions for Extraction Pipeline
- **Action**: Added `RUN.md` and `run_pipeline.py`

## [2026-05-25 9:54 AM - 12:40 PM] - Assessing Data Quality and Exploring Possible Approaches
- **Thought Process**:
  - Based on Reznar's hypothesis, his catalog might not be priced appropriately due to items that don't belong in their rarity. This indicates that the rarity field is noisy as some of them might be mislabeled.
  - Since the rarity itself is an ordinal variable, we could try ordinal based models or simply treat them as different class/categories. Ordinal Logistic Regression might work, but I have to confirm whether the data satisfy the model's assumption or not.
  - Treating it as multiclass classification problem comes with its own problem like class imbalances and losing the sense of how far the "error" is. As it treats every rarity as its own class, it assumes the error between "uncommon" and "rare" to be exact same as "uncommon" and "artifact", which is not the case.
  - Treating them as regression problem might be worth a shot and use some sort of rounding to classify. This keeps the sense of how "far" the error between rarities.

## [2026-05-25 3:12 PM - 4:05 PM] - Planned 3 Approaches with Pros and Cons
- Things I have to consider are: small data (80 items), class imbalance, non linear features, ordinal target value, and possible noisy/mislabeled target value. 
- With the limitations above, there are a couple of approaches I could think of:
  - Ordinal Logistic Regression: 
    - Natively handle ordinal values.
    - Has strong assumptions, which could be hard to satisfy since the data is small and heavily imbalanced.
  - Treat target as multiclass/categorical: 
    - Could use tree models like Random Forest or XGB that are robust and don't have a lot of assumptions.
    - No sense of how "far" the errors are and all error is considered equal.
  - Treat target as regression/nominal: 
    - Could also use tree models that are robust with weak assumptions.
    - The sense of how "far" the error is preserved.
    - Might have to add another rounding layer to classify results.


## [2026-05-25 4:13 PM - 5:03 PM] - Selecting and Transforming Features for Analysis
- **Action:** Transformed features from postgres database to be ready for analysis 
- **Action:** Removed `common` from `Rarity` enum as it does not exist in the extracted data.
- **Thought Process**:
  - Intuitively, fields like form and slot are not necessarily meaningful for rarity. Any form could have any rarity and can be worn anywhere. Thus, will not be used for prediction.
  - On the other hand, for fields that are lists, encoding each types would also not be reasonable since most of them are sparse, very specific, and free form texts. So, using just the length of the lists would make more sense and enough to capture the bigger picture of each items. 
  - Another thing to mention is that, there is one item "Pouch of False Coins" that happens to have multiple rarity (varies) depending on the coin types. This is not captured in the parser and dropped in prediction as the difference between its rarities is overly specific. Splitting them into separate rows/items would only cause more issues in the long run and not worth the complexity.
  - To handle multicollinearity that can mess with stability, a simple Pearson's correlation filtering is used.

## [2026-05-25 6:03 PM - 9:06 PM] - Testing Approaches and Models' Assumptions
- **Action:** Tested the Ordinal Logistic Regression and Random Forest (multiclass) approach. 
- **Thought Process**:
  - Ordinal Logistic Regression assumption of proportional odds didn't seem to be satisfied here. However, since the target label itself could be noisy and mislabeled, it is difficult to tell whether the assumptions are truly violated or not.
  - The multiclass Random Forest test confirmed the same. Using out-of-fold stratified k-fold (k=4), it looks like the model is doing poorly. But again, it is hard to determine what actually causes it. It could be due to the fact that the model wasn't able to capture the patterns and didn't learn well, or simply because the items are mislabeled.
  - This indicates that relying on one model is a bad idea. To better handle the noisy labeling is to do an ensemble across models with different architectures.
  - Additionally, framing the problem towards regression instead of classification allows more refined results between models and preserve the distance in terms of errors. 


## [2026-05-26 3:23 PM – 4:49 PM] - RF + Ridge Regression Ensemble Approach
- **Action:** Built the approach in `reznar/analysis.ipynb` using RF regressor + Ridge regressor and trained with `RepeatedStratifiedKFold` for OOF predictions. To handle the imbalance, model's internal weighting is used with weights of `1/N`.
- **Action:** Evaluated both with ordinal aware metrics on the OOF predictions: macro-MAE, Spearman correlation, Quadratic Weighted Kappa (QWK), and ±1-accuracy (predictions off-by-1 is considered true).
- **Action:** Added VIF (Variance Inflation Factor) filtering which iteratively drops the feature with the highest VIF until all remaining features have VIF < 5.
- **Thought Process**:
  - Framing it as regression instead of classification preserves the distance of errors, so predictions that is off-by-3 is penalized more than the ones that is off-by-1. Also, we get a continuous score to rank by.
  - Using two architecturally different model reduces both the bias and variance of the prediction that might occur due to the noisy label. So if both model agree on the prediction, it is more trustworthy than either alone.
  - Since we are focusing more on the predictive power and not inference, the assumptions check Ridge Regression are relaxed and we focus more on robust validation for generalization. 
  - To make sure we preserve the sense of distance in errors, I used ordinal aware metrics like MAE, Spearman correlation, and Quadratic Weighted Kappa (QWK). They penalize errors that are further more and errors that are closer less. ±1-accuracy is also used to get a better sense how far off the predictions are, in this case, we assume errors within a level are true. If the ±1-accuracy is low, that means the model predictions are spread widely across rarities, which could be an indicator that the model fails to capture the pattern. However, if it is high, it could mean that the items that are predicted more than a level off is the outlier items that don't belong in their rarity tier.
  - Spearman correlation metric is used here to check if the model gets the ranking right without relying on the raw prediction values. Since we frame this as regression problem, we get continuous output instead of integers. Thus, relying on the raw prediction values or rounding them instead could introduce more bias. 
  - Also, since we are using Ridge Regression, VIF filtering is added after correlation filtering to have more robust multicollinearity handling.
- **Findings**:
  - Both models seem to have real signal. The Ridge Regression and RF model perform similarly on every metric (macro-MAE 0.695 vs 0.743, Spearman +0.531 vs +0.560, QWK 0.553 vs 0.550, ±1-acc 0.924 vs 0.949).
  - RF prediction range is compressed to [0.39, 3.28], which means it cannot reach `legendary` (3) or `artifact` (4). While Ridge prediction range is [0.40, 5.45] that can reach the top but over extrapolate over the max of 4.
  - The two "drawbacks" seems to complement each other. The RF smooths the tails down while the Ridge extrapolates them up. Thus, averaging them together gives a middle estimate that's reasonable in the bulk (`rare` and `very_rare`) but noisy at the extremes (`uncommon`, `legendary`, and `artifact`).
  - This prediction is fundamentally limited by data itself, where we have 9 legendary and 4 artifact items, which is not enough to learn a sharp boundary at the edges regardless of the model. 