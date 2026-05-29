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
- Also, because of the small amount of data we have, deep learning is ruled out since it would overfit. Hence, we start with simple models and only add complexity if needed.
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
  - This also indicates that relying on one model is a bad idea. To better handle the noisy labeling is to do an ensemble across models with different architectures.
  - Additionally, framing the problem towards regression instead of classification seems to allow more refined results between models and preserve the distance in terms of errors. 


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
  - RF prediction range is compressed to [0.39, 3.28], which means it cannot reach `artifact` (4). While Ridge prediction range is [0.40, 5.45] that can reach the top but over extrapolate over the max of 4.
  - The two "drawbacks" seems to complement each other. The RF smooths the tails down while the Ridge extrapolates them up. Thus, averaging them together gives a middle estimate that's reasonable in the bulk (`rare` and `very_rare`) but noisy at the extremes (`uncommon`, `legendary`, and `artifact`).
  - This prediction is fundamentally limited by data itself, where we have 9 legendary and 4 artifact items, which is not enough to learn a sharp boundary at the edges regardless of the model. 


## [2026-05-27 9:50 AM – 1:38 PM] - Model Comparison and Validation Across Framings
- **Action:** Added ordinal LR (`mord.LogisticAT`) as a quick sanity check and third opinion alongside the RF classifier and RF + Ridge regressors.
- **Action:** Compared all framings against a mean baseline under `RepeatedStratifiedKFold` of 4×5 (4 fold repeated 5x) and weighting to handle imbalance, which then scored with ordinal-aware metrics (macro-MAE, QWK, Spearman, ±1-acc).
- **Action:** Ran an in-depth per-class diagnostic with signed residual (pred − true) and mean prediction per class to expose each model's directional bias and how well it handle the imbalance.
- **Thought Process**:
  - Since the proportional-odds check was inconclusive (we can't tell a true violation from noisy labels), I decided to fit the Oridinal Logistic Regression `LogisticAT` as a quick sanity check and third opinion. Similar to the case with Ridge regression, we are more focused on the predicitve power than inference, hence, there's no harm in trying to fit the model in case it works well despite failing to meet the assumptions. However, a more in-depth validation and diagnostic is required to make sure it actually captures a signal.
  - So, to have a more clear picture on the model predictions themselves, I added per-class signed residual and mean prediction, which enables us to see which rarity the model over or under predict. Additionally, this also shows how well the weighting works against the class imbalance.
  - As a final comparison across framings and models, I train and evaluate them once more with using the same method `RepeatedStratifiedKFold` and the same weighting of `1/N`. I also added a baseline model that always predicts the average rarity as a sanity check that ensure each model is actually learning and not just fitting through the noise.
  - Since OLR and RF classification models outputs class and probabilities instead of continuous variable like regression, I calculated the expected value using the probabilities to make them comparable with other regression models. However, this comes with a caveat that it introduces bias as it depends on how confident the model in its prediction while also naturally pulls the predictions towards the average. Despite that, it could still gives us a rough idea in how well the models fit in comparison to regression models.
- **Findings**:
  - All models beat the baseline. RF regression, Ridge, and OLR carry the most signal.
  - RF classification seems to underperform against every other models across all metrics. The per-class mean prediction reveals that the model struggle to cover lower and upper tiers like uncommon, legendary, and artifact. The signed residual also reveals that the predictions for those minority tiers are being biased towards the majority tiers (rare and very rare). 
  - On the other hand, the OLR performs as good as the other regression models despite using expected value for its metrics. The per-class signed residual and mean prediction reveals that it is quite confident in the predictions, covers a good range, and handle the imbalances quite well. It performs similarly to the ridge regression model, it handled the top rarities (legendary and artifact) predictions quite well, but underperform in the lower rarity (uncommon) range.
  - However, RF regression model is the complete opposite from OLR and Ridge. It underperformed in top rarities predictions and handled the lower rarity predictions better. We can see it from the uncommon rarity mean prediction and signed residual that it reaches lower value in average compared to OLR and Ridge, and struggles to reach the artifact rarity. This relates to the previous test where the prediction range is compressed to [0.39, 3.28], indicating it is struggling in predicting the top range of rarities. Despite that, the metrics shows that it is comparable with the OLR and Ridge models. Hence, the OLR, Ridge, and RF regression models are the most reasonable models to ensemble together as they complement each other weaknesses.


## [2026-05-27 11:05 PM - 2026-05-28 1:34 AM] - Replaced Expected-Value Scoring with Hard Predictions and Reran Validation
- **Action**: Dropped the expected-value scoring for the classification and ordinal models and simplified `oof_predict` so every model is now evaluated by its own hard `.predict()` output.
- **Thought Process**:
  - Expected value was originally used only to make probability based models on a continuous scale, making it comparable to the regression models. However as mentioned previously, expected value introduces bias and it pulls the predictions toward the center, so it might not represent how well the model actually performs. This bias is unnecessary when what we want is raw predictive power.
  - The one caveat is that classification models output integer predictions, which can look artificially strong on a metric like MAE (which is why MAE is not the standard metric in evaluation classification model). However, this is reasonable in our case as we are also looking at different metrics to see the bigger picture.
- **Findings**:
  - The effect on RF-clf was quite significant. It went from looking like the weakest model to one of the strongest. Its macro-MAE dropped from ~0.81 to ~0.55, which is the best across other models. Its per-class signed residual and mean prediction also improved and is even comparable with the Ordinal LR.
  - This shifted my focus back towards the classification framing instead of the regression. Despite of them not having the sense of distance in terms of errors, the spearman metric from the RF classification model tells another story. While it is not as good as the OLR or RF regression, it is still comparable and it shows that it is able to capture the "order" as well as the others. 



## [2026-05-28 9:42 AM - 10:44 AM] - Final Model - Ensemble RF Regression + OLR
- **Action**: Committed to the regression framing and built the final RF-reg + OLR ensemble with simple unweighted mean of their OOF scores.
- **Action**: Ran error analysis across the three regression models (RF-reg, Ridge, OLR) using Pearson correlation on both their predictions and their residuals. then re-ran the ensemble through the identical OOF harness and metrics.
- **Thought Process**:
  - Despite having good macro-MAE and QWK metrics, RF Classification lacks in ±1-acc and how well it can rank. Low ±1-acc means there's more spread in the predictions across class, and since our labeling is noisy, it could just be an overfit and it capture the noise instead of signal. It is also shown in the per-class signed residual and prediction mean, where the artifact class is predicted perfectly. This raises my suspicion, especially when the artifact tier only have 4 items in it.
  - Furthermore, since we are going to use it for anomaly detection, we still want the fine gradient to rank on instead of the hard integer labels that classification gives us. Only the regression models can provide a continuous score to rank anomaly severity in a more finer way.
  - The error analysis step is to decide which models genuinely add diversity. Averaging two models that make the same errors would not be beneficial, so the residual correlation matters more than the prediction correlation. Like mentioned before, the point of the ensemble is that two diverse architectures agreeing on a disagreement is stronger evidence of a real anomaly than either model alone.
- **Findings**:
  - As expected, Ridge and OLR are the most correlated pair on both views (predictions r=0.94, residuals r=0.92). In essence, they are both linear model and have similar architecture, thus, keeping both of them is redundant. 
  - Decided to drop Ridge and kept OLR. OLR wins on QWK (0.603 vs 0.553), Spearman (0.563 vs 0.531), and reaches further into the tails. Furthermore, the OLR gives advantage of natively handling ordinal target instead of just regressing through it. Hence, the final ensemble pairs are RF-reg with OLR.
  - The ensemble improves exactly where it matters. It achieves Spearman 0.595 (best of any model) and ±1-acc 0.962 (ties best). QWK is unchanged (0.600), and macro-MAE dips slightly (0.679 vs 0.650) since averaging pulls the extremes toward the middle, so the tails lose a little reach. That same smoothing also balances the per-class bias, where at every tier of the ensemble's signed residual sits between its two models.
  - From here, we can use the ensemble to do both prediction and anomaly detection in finding which items do not belong in their rarity tier.

## [2026-05-28 11:11 AM – 12:13 PM] - Refined Prompt for Special Effects, Drawbacks, and Charges
- **Action**: Refined extraction prompt in `reznar/extract.py` and field descriptions in `reznar/ontology.py` to fix inconsistent `special_effects` and `drawbacks` extraction.
- **Thought Process**:
  - `special_effects` length is highly correlated with rarity, which doesn't mean the one that is the most significant in making predictions. However, it is still important to keep them clean as much as possible. Thep previous prompt gives inconsistent details that contains duplicates, over-splitting, over-merging which adds more noise.
  - Thus, after a couple of runs and iterations of prompt, it was able to structure them more clearly and slightly increases the prediction power across models.


## [2026-05-28 6:20 PM – 7:20 PM] - Detecting Anomalies
- **Action**: Built the anomaly detection step in `reznar/analysis.ipynb` on top of the RF-reg + OLR ensemble. Scored every item with the ensemble OOF prediction, rounded it to the nearest tier, computed `off_by = predicted_tier - actual_tier`, and flagged items with `|off_by| >= 2` as anomalies.
- **Thought Process**:
  - The continuous ensemble score is exactly what makes this more refined. Rounding it gives a predicted tier to compare against the label, while the underlying score preserves the fine gradient to rank severity by.
  - Abusing the model high ±1-accuracy, I flagged the items that are two or more tiers off than the predictions, which means that the model "truly" disagree with the assigned rarity. A model with high ±1-accuracy would not predict it more than two tiers off if the item really belongs in the rarity tier.
  - However, this ensemble produces a list of suspects, not a conclusion. There is always some biased involved no matter what, hence, the final call on whether an item is mislabeled, genuinely unusual, or a model miss is left to human review against the source listing.
- **Findings**:
  - Two items cross the threshold, both under-rated by two tiers:
    - **Universal Scroll** (`legendary`, predicted `rare`): repeatable but fixed single-spell utility with no new capability, closer to `rare` than legendary.
    - **Horn of Bronze Dragon Control** (`very_rare`, predicted `uncommon`): one narrow effect against a single creature type with no combat bonus or attunement.