from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    ANTHROPIC_API_KEY: str
    GITHUB_TOKEN: str
    REPOS_DIR: str = "/tmp/repos"
    DB_PATH: str = "./data/runs.db"
    CONSTITUTION_CACHE_DIR: str = "./cache/constitutions"
    FRONTEND_URL: str = "http://localhost:5173"
    PORT: int = 8000
    MAX_REVISION_ROUNDS: int = 3
    MAX_AGENT_ITERATIONS: int = 25
    MODEL: str = "claude-sonnet-4-20250514"

    class Config:
        env_file = ".env"


config = Settings()
