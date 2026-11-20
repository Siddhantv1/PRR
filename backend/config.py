from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # "gemini", or "openai" for any OpenAI-compatible API (Groq, OpenRouter, Ollama)
    LLM_PROVIDER: str = "gemini"
    GOOGLE_API_KEY: str = ""
    OPENAI_BASE_URL: str = "https://api.groq.com/openai/v1"
    OPENAI_API_KEY: str = ""
    GITHUB_TOKEN: str
    REPOS_DIR: str = "/tmp/repos"
    DB_PATH: str = "./data/runs.db"
    CONSTITUTION_CACHE_DIR: str = "./cache/constitutions"
    FRONTEND_URL: str = "http://localhost:5173"
    PORT: int = 8000
    MAX_REVISION_ROUNDS: int = 2
    MAX_AGENT_ITERATIONS: int = 25
    MODEL: str = "gemini-3.1-flash-lite"

    class Config:
        env_file = ".env"


config = Settings()
