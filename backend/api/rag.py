"""RAG (Retrieval Augmented Generation) API"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import List, Optional

from backend.database import get_db
from backend.models.user import User
from backend.api.auth import get_current_user
from backend.ml.embeddings import embedding_service
from backend.ml.llm import llm_service

router = APIRouter()


class QueryRequest(BaseModel):
    query: str
    top_k: int = 5


class AddDocumentRequest(BaseModel):
    content: str
    metadata: Optional[dict] = None


class AnswerRequest(BaseModel):
    question: str
    context_docs: int = 3


@router.post("/query")
async def query_documents(
    request: QueryRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Query document index using semantic search
    Returns relevant documents
    """
    results = embedding_service.search(
        query=request.query,
        top_k=request.top_k
    )

    return {
        "query": request.query,
        "results": [
            {
                "document": doc,
                "distance": dist,
                "metadata": meta
            }
            for doc, dist, meta in results
        ]
    }


@router.post("/add-document")
async def add_document(
    request: AddDocumentRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Add document to vector index
    """
    embedding_service.add_documents(
        documents=[request.content],
        metadata=[request.metadata] if request.metadata else None
    )

    return {
        "message": "Document added successfully",
        "total_documents": len(embedding_service.documents)
    }


@router.post("/answer")
async def answer_question(
    request: AnswerRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Answer question using RAG:
    1. Retrieve relevant documents
    2. Generate answer with LLM
    """
    # Retrieve relevant documents
    results = embedding_service.search(
        query=request.question,
        top_k=request.context_docs
    )

    if not results:
        return {
            "question": request.question,
            "answer": "No relevant information found in the knowledge base.",
            "sources": []
        }

    # Combine context
    context = "\n\n".join([doc for doc, _, _ in results])

    # Generate answer with LLM
    answer = llm_service.answer_question(
        question=request.question,
        context=context
    )

    return {
        "question": request.question,
        "answer": answer,
        "sources": [
            {
                "content": doc[:200] + "...",
                "relevance": float(dist)
            }
            for doc, dist, _ in results
        ]
    }


@router.post("/generate-query-plan")
async def generate_query_plan(
    request: QueryRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Convert natural language query to structured query plan
    """
    plan = llm_service.generate_query_plan(request.query)

    return {
        "query": request.query,
        "plan": plan
    }


@router.get("/stats")
async def get_rag_stats(
    current_user: User = Depends(get_current_user)
):
    """
    Get RAG system statistics
    """
    return {
        "total_documents": len(embedding_service.documents),
        "embedding_model": embedding_service.model_name,
        "llm_model": llm_service.model_name,
        "index_dimension": embedding_service.model.get_sentence_embedding_dimension() if embedding_service.model else 0
    }


@router.delete("/clear-index")
async def clear_index(
    current_user: User = Depends(get_current_user)
):
    """
    Clear all documents from index
    """
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    embedding_service.clear_index()

    return {
        "message": "Index cleared successfully"
    }
