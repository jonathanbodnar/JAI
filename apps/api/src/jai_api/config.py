"""Centralized typed config. Reads from .env or process env."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- LLM ---
    openrouter_api_key: str = ""
    openrouter_app_name: str = "jai"
    openrouter_app_url: str = "https://jai.local"

    # Model registry (role → OpenRouter slug). Override in env.
    jai_model_orchestrator: str = "qwen/qwen3.7-max"
    jai_model_reflection: str = "moonshotai/kimi-k2.6"
    jai_model_strategy: str = "deepseek/deepseek-v4-pro"
    jai_model_skill_builder: str = "qwen/qwen3.7-max"
    jai_model_fast: str = "deepseek/deepseek-v4-flash:free"
    jai_model_embed: str = "openai/text-embedding-3-large"

    # --- Speech ---
    groq_api_key: str = ""
    elevenlabs_api_key: str = ""
    kokoro_tts_url: str = "http://localhost:8880"

    # --- Memory ---
    mem0_api_key: str = ""
    mem0_org_id: str = ""
    mem0_project_id: str = ""

    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str = ""
    qdrant_collection: str = "jai_memory"

    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "jai-dev-password"
    neo4j_database: str = "neo4j"

    # --- App DB / Auth ---
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""
    supabase_jwt_secret: str = ""
    database_url: str = ""

    # --- Blobs ---
    r2_account_id: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket: str = "jai-blobs"
    r2_public_url: str = ""

    # --- Sandbox ---
    cloudflare_account_id: str = ""
    cloudflare_api_token: str = ""
    sandbox_base_url: str = ""
    sandbox_auth_token: str = ""

    # --- Credentials encryption ---
    jai_credentials_key: str = ""

    # --- MCP gateway ---
    jai_mcp_server_token: str = ""    # bearer for our own MCP server

    # --- Google OAuth ---
    google_oauth_client_id: str = ""
    google_oauth_client_secret: str = ""
    google_oauth_redirect_uri: str = "https://api.ftr.me/auth/google/callback"

    # --- Observability ---
    langsmith_api_key: str = ""
    langsmith_project: str = "jai"
    langsmith_tracing: bool = False  # set true to enable

    # --- App ---
    jai_user_id: str = ""           # single-tenant dev override
    jai_backend_url: str = "https://api.ftr.me"
    jai_frontend_url: str = "https://app.ftr.me"
    cors_origins: list[str] = Field(default_factory=lambda: [
        "https://app.ftr.me",
        "https://jai.ftr.me",
        "http://localhost:3000",
    ])
    # Allow any *.up.railway.app preview URL (Railway free deploys) and any
    # *.ftr.me host (covers app./api./tts. and future subdomains).
    cors_origin_regex: str = r"https://([a-z0-9-]+\.)*(up\.railway\.app|ftr\.me)$"

    # --- Memory tuning ---
    working_window_size: int = 20
    mem0_top_k: int = 8
    qdrant_top_k: int = 5
    neo4j_hops: int = 1


@lru_cache
def get_settings() -> Settings:
    return Settings()
