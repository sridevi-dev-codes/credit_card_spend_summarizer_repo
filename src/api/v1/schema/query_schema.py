from pydantic import BaseModel, Field
from typing import Optional


class QueryRequest(BaseModel):
    query: str = Field(..., description="User question")
    session_id: str = Field(..., description="Unique chat session id")

class QueryResponse(BaseModel):
    query: str
    answer: str
    policy_citations: str
    page_no: str
    document_name: str
    route: str
    sql_query_executed: Optional[str] = None


class AIResponse(BaseModel):
   query: str = Field(description="The Given query by user must be present here")
   answer: str = Field(description="The generated response")
   policy_citations: str = Field(description="Give the Policy Citation (for document queries)")
   page_no: str = Field(description="The page number in the metadata")
   document_name: str = Field(description="Name of the document used")
   route: str = Field(description="transaction, document, greeting, unsupported")
   sql_query_executed: Optional[str] = Field(default=None, description="SQL generated for transaction questions")