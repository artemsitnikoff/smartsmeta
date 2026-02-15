import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

VERSION = "0.2.0"

GPT_MODEL = "gpt-5.2-pro"

DEFAULT_RATES = {
    "PM": 4000, "Аналитик": 4500, "Дизайнер": 4000,
    "TechLead": 5500, "Frontend": 4500, "Backend": 4500,
    "Mobile": 4500, "QA": 3500, "DevOps": 5000,
    "DataEngineer": 5000, "DataAnalyst": 4000,
    "GIS": 4500, "Writer": 3000,
}
