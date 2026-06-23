from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # API Keys
    anthropic_api_key: str
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # Database
    database_url: str = "sqlite+aiosqlite:///./trading.db"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Trading config
    portfolio_value: float = 10000.0
    max_risk_per_trade: float = 0.01
    max_daily_risk: float = 0.03
    min_signal_score: float = 70.0
    min_confidence: float = 0.65
    min_rr: float = 2.5

    # Assets
    symbols: str = "BTCUSDT,ETHUSDT,SOLUSDT"

    # Environment
    environment: str = "development"
    log_level: str = "INFO"

    @property
    def symbol_list(self) -> list[str]:
        return [s.strip() for s in self.symbols.split(",")]

    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"


settings = Settings()
