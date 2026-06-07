from pathlib import Path
import shutil

from fastapi import UploadFile

from src.ingestion.ingestion import run_ingestion

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)


def upload_and_ingest(file: UploadFile):

    file_path = DATA_DIR / file.filename

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    return run_ingestion(str(file_path))