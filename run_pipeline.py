"""Run the full extraction pipeline: PDF → items_raw.json → Postgres."""

from reznar.extract import main as extract
from reznar.parser import main as parse

if __name__ == "__main__":
    print("Stage 1: PDF → items_raw.json")
    parse()
    print("\nStage 2: items_raw.json → Postgres")
    extract()
