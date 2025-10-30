"""
Embedding service using sentence-transformers (free OSS)
Model: all-MiniLM-L6-v2 (384 dimensions, fast and efficient)
"""
from sentence_transformers import SentenceTransformer
import numpy as np
import faiss
import pickle
import os
from typing import List, Tuple, Optional
import logging
from pathlib import Path

from backend.config import settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    """
    Manages embeddings using sentence-transformers + FAISS
    All free and open-source
    """

    def __init__(self):
        self.model_name = settings.EMBEDDING_MODEL
        self.model: Optional[SentenceTransformer] = None
        self.index: Optional[faiss.IndexFlatL2] = None
        self.index_path = Path(settings.FAISS_INDEX_PATH)
        self.documents: List[str] = []
        self.metadata: List[dict] = []

    async def initialize(self):
        """Load embedding model and FAISS index"""
        logger.info(f"Loading embedding model: {self.model_name}")

        # Load sentence-transformers model (downloads if first time)
        self.model = SentenceTransformer(self.model_name)

        logger.info(f"Embedding model loaded. Dimension: {self.model.get_sentence_embedding_dimension()}")

        # Create or load FAISS index
        self.index_path.parent.mkdir(parents=True, exist_ok=True)

        if self._index_exists():
            self._load_index()
        else:
            self._create_index()

        logger.info("Embedding service initialized")

    def _index_exists(self) -> bool:
        """Check if saved index exists"""
        return (
            (self.index_path / "index.faiss").exists() and
            (self.index_path / "documents.pkl").exists()
        )

    def _create_index(self):
        """Create new FAISS index"""
        dimension = self.model.get_sentence_embedding_dimension()
        self.index = faiss.IndexFlatL2(dimension)
        self.documents = []
        self.metadata = []
        logger.info(f"Created new FAISS index with dimension {dimension}")

    def _load_index(self):
        """Load existing FAISS index"""
        try:
            self.index = faiss.read_index(str(self.index_path / "index.faiss"))

            with open(self.index_path / "documents.pkl", "rb") as f:
                data = pickle.load(f)
                self.documents = data["documents"]
                self.metadata = data["metadata"]

            logger.info(f"Loaded FAISS index with {len(self.documents)} documents")
        except Exception as e:
            logger.error(f"Error loading index: {e}")
            self._create_index()

    def _save_index(self):
        """Save FAISS index to disk"""
        try:
            self.index_path.mkdir(parents=True, exist_ok=True)

            faiss.write_index(self.index, str(self.index_path / "index.faiss"))

            with open(self.index_path / "documents.pkl", "wb") as f:
                pickle.dump({
                    "documents": self.documents,
                    "metadata": self.metadata
                }, f)

            logger.info("FAISS index saved")
        except Exception as e:
            logger.error(f"Error saving index: {e}")

    def encode(self, texts: List[str]) -> np.ndarray:
        """Encode texts to embeddings"""
        embeddings = self.model.encode(texts, convert_to_numpy=True)
        return embeddings

    def add_documents(self, documents: List[str], metadata: Optional[List[dict]] = None):
        """
        Add documents to FAISS index
        """
        if not documents:
            return

        # Encode documents
        embeddings = self.encode(documents)

        # Add to FAISS
        self.index.add(embeddings.astype('float32'))

        # Store documents and metadata
        self.documents.extend(documents)

        if metadata:
            self.metadata.extend(metadata)
        else:
            self.metadata.extend([{}] * len(documents))

        # Save index
        self._save_index()

        logger.info(f"Added {len(documents)} documents to index. Total: {len(self.documents)}")

    def search(
        self,
        query: str,
        top_k: int = 5
    ) -> List[Tuple[str, float, dict]]:
        """
        Search for similar documents
        Returns list of (document, distance, metadata)
        """
        if len(self.documents) == 0:
            return []

        # Encode query
        query_embedding = self.encode([query])

        # Search FAISS
        distances, indices = self.index.search(query_embedding.astype('float32'), top_k)

        # Collect results
        results = []
        for dist, idx in zip(distances[0], indices[0]):
            if idx < len(self.documents):
                results.append((
                    self.documents[idx],
                    float(dist),
                    self.metadata[idx]
                ))

        return results

    def clear_index(self):
        """Clear all documents from index"""
        self._create_index()
        self._save_index()
        logger.info("Index cleared")


# Global singleton
embedding_service = EmbeddingService()
