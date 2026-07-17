"""Configuration management"""
import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    # Database
    DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/semantic_layer")
    
    # OpenAI
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
    OPENAI_MODEL_FAST = os.getenv("OPENAI_MODEL_FAST", "gpt-4o-mini")
    
    # Service
    SERVICE_PORT = int(os.getenv("SERVICE_PORT", "9000"))
    SERVICE_NAME = "Semantic Layer Service"
    VERSION = "1.0.0"
    
    # Schema
    METADATA_TABLE = "semantic_metadata"
    SCHEMA_VERSION_TABLE = "schema_versions"

    # Pinecone Vector Store
    PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
    PINECONE_INDEX = os.getenv("PINECONE_INDEX", "sales-agent")

settings = Settings()
