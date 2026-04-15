from functools import lru_cache
from typing import Any, Dict, Optional
from pydantic import PostgresDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """Application settings."""
    
    # Supabase credentials
    SUPABASE_URL: str
    SUPABASE_KEY: str
    
    # Database URL (Supavisor connection string)
    DATABASE_URL: str
    
    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def validate_database_url(cls, v: Any) -> str:
        """
        Validate and fix the DATABASE_URL.
        Prefixes with 'postgresql+asyncpg://' if standard 'postgres://' or 'postgresql://' is provided.
        """
        if isinstance(v, str):
            if v.startswith("postgres://"):
                return v.replace("postgres://", "postgresql+asyncpg://", 1)
            if v.startswith("postgresql://") and not v.startswith("postgresql+asyncpg://"):
                return v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v

    # API configuration
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "Stock Monitoring Agent"
    
    # LangChain / Google Gemini (for LangGraph)
    GOOGLE_API_KEY: Optional[str] = None
    
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="ignore"
    )

@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings() # type: ignore
