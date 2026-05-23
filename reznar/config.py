import os

from dotenv import load_dotenv

load_dotenv()

VISION_MODEL: str = os.environ["VISION_MODEL"]
ANALYSIS_MODEL: str = os.environ["ANALYSIS_MODEL"]
