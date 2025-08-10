"""
Text embedding utilities for semantic search
"""
from typing import List
import numpy as np
import logging

logger = logging.getLogger(__name__)

# Try to import sentence transformers
try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False
    logger.warning("sentence-transformers not available. Install with: pip install sentence-transformers")

# Global model instance
_model = None

def get_model():
    """Get or initialize the sentence transformer model"""
    global _model
    if _model is None:
        if not SENTENCE_TRANSFORMERS_AVAILABLE:
            logger.warning("sentence-transformers not available, using simple embeddings")
            _model = "simple"
            return _model
            
        try:
            # Use a lightweight model for embeddings
            _model = SentenceTransformer('all-MiniLM-L6-v2')
            logger.info("Loaded sentence transformer model: all-MiniLM-L6-v2")
        except Exception as e:
            logger.error(f"Failed to load sentence transformer model: {e}")
            # Fallback to a simple hash-based embedding
            _model = "simple"
    return _model

def embed_texts(texts: List[str]) -> List[List[float]]:
    """
    Convert a list of texts to embeddings using sentence transformers.
    
    Args:
        texts: List of text strings to embed
        
    Returns:
        List of embedding vectors (lists of floats)
    """
    model = get_model()
    
    if model == "simple":
        # Simple fallback: create hash-based embeddings
        logger.warning("Using simple hash-based embeddings as fallback")
        embeddings = []
        for text in texts:
            # Create a simple deterministic embedding based on text hash
            hash_val = hash(text)
            # Convert to a 384-dimensional vector (matching all-MiniLM-L6-v2)
            embedding = []
            for i in range(384):
                embedding.append(float((hash_val + i) % 1000) / 1000.0)
            embeddings.append(embedding)
        return embeddings
    
    try:
        # Use sentence transformers for real embeddings
        embeddings = model.encode(texts)
        # Convert numpy arrays to lists for JSON serialization
        return [emb.tolist() for emb in embeddings]
    except Exception as e:
        logger.error(f"Error creating embeddings: {e}")
        # Fallback to zero vectors
        return [[0.0] * 384 for _ in texts]
