from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from requests import request
from src.api.v1.services.query_service import query_documents,query_documents_stream
from fastapi.responses import StreamingResponse

router = APIRouter()


class QueryRequest(BaseModel):
    query: str
    session_id: str


@router.post("/query")
def query(req: QueryRequest):
    try:
        result = query_documents(req.query, req.session_id)
        return result

    except Exception as e:
        # log if needed
        raise HTTPException(
            status_code=500,
            detail=f"Query pipeline failed: {str(e)}"
        )


@router.post("/query/stream")
async def query(req: QueryRequest):
    print ("Calling query_documents_stream with query:", req.query)
    try:
        generator = await query_documents_stream(req.query, req.session_id)
        print(f"Generator created for query--ROUTER: {req.query}")
        return StreamingResponse(generator, media_type="text/event-stream")

    except Exception as e:
        # log if needed
        raise HTTPException(
            status_code=500,
            detail=f"Query pipeline failed: {str(e)}"
        )
