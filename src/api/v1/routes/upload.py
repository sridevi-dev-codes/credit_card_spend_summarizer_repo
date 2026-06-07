from fastapi import APIRouter, UploadFile, File

from src.api.v1.services.upload_service import upload_and_ingest

router = APIRouter()

@router.post("/upload-pdf")
async def upload_pdf(file: UploadFile = File(...)):
    result = upload_and_ingest(file)

    return {
        "message": "PDF ingested successfully",
        "result": result
    }