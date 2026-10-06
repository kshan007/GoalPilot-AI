"""
Configuration settings for GoalPilot Application.
Handles paths to GoalPilot_AI research artifacts dynamically.
"""

import os
from pathlib import Path
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    API_PORT: int = 8000
    API_HOST: str = "127.0.0.1"
    DEBUG: bool = True
    CORS_ORIGINS: List[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ]

    GOALPILOT_AI_PATH: str = os.getenv("GOALPILOT_AI_PATH", "")

    def get_goalpilot_ai_dir(self) -> Path:
        """Resolves the absolute path to GoalPilot_AI."""
        if self.GOALPILOT_AI_PATH:
            p = Path(self.GOALPILOT_AI_PATH)
            if not p.is_absolute():
                p = (Path(__file__).resolve().parent.parent.parent / p).resolve()
            if p.exists():
                return p

        candidates = [
            Path(__file__).resolve().parent.parent.parent.parent / "GoalPilot_AI",
            Path("s:/fyp/GoalPilot_AI"),
            Path("./GoalPilot_AI"),
            Path("../GoalPilot_AI"),
        ]

        for cand in candidates:
            if cand.exists():
                return cand.resolve()

        return (Path(__file__).resolve().parent.parent.parent.parent / "GoalPilot_AI").resolve()

settings = Settings()
