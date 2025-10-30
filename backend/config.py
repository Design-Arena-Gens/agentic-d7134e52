"""Configuration management using pydantic settings"""
from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional
import os


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = Field(
        default="postgresql://healthcare:healthcare123@localhost:5432/healthcare_ai"
    )
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 10

    # Security
    JWT_SECRET_KEY: str = Field(default="dev-secret-key-change-in-production")
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    ENCRYPTION_KEY: str = Field(default="dev-encryption-key-32-bytes-long!")

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # NPI Registry (free public API)
    NPI_REGISTRY_BASE_URL: str = "https://npiregistry.cms.hhs.gov/api/"
    NPI_RATE_LIMIT_SECONDS: float = 1.0

    # Nominatim (OpenStreetMap - free geocoding)
    NOMINATIM_BASE_URL: str = "https://nominatim.openstreetmap.org"
    NOMINATIM_USER_AGENT: str = "healthcare-ai-system/1.0"
    NOMINATIM_RATE_LIMIT_SECONDS: float = 1.0

    # ML Models (all free OSS)
    EMBEDDING_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"
    LLM_MODEL: str = "TinyLlama/TinyLlama-1.1B-Chat-v1.0"
    FAISS_INDEX_PATH: str = "./data/faiss_index"

    # Observability
    LOG_LEVEL: str = "INFO"
    METRICS_PORT: int = 9090

    # Environment
    ENVIRONMENT: str = "development"

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
