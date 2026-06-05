"""
Hey Gaadi — Multilingual In-Car Voice Assistant
Main entry point. Starts the Pipecat pipeline.
Run: python main.py
"""

import asyncio
import os
from dotenv import load_dotenv
from pipeline.pipeline import run_pipeline

load_dotenv()

if __name__ == "__main__":
    print("🚗 Hey Gaadi starting...")
    print("Say 'Hey Gaadi' to activate the assistant.")
    asyncio.run(run_pipeline())
