from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Legal WhatsApp Assistant"
    app_env: str = "local"
    office_name: str = "TN advocacia"
    local_timezone: str = "America/Maceio"
    database_url: str = "mysql+pymysql://user:password@localhost:3306/legal_assistant"
    anthropic_api_key: str | None = None
    claude_model: str = "claude-sonnet-4-6"
    default_organization_id: int = 1
    ai_temperature: float = 0.2
    auto_reply_enabled: bool = True
    follow_up_enabled: bool = True
    follow_up_delay_hours: int = 1
    crm_session_secret: str = "tn-crm-local-secret"
    crm_self_registration_enabled: bool = True
    crm_admin_email: str = "atendimento@example.com"
    crm_admin_password: str = "admin123"
    crm_seed_demo_users: bool = True
    meta_graph_api_version: str = "v23.0"
    meta_whatsapp_verify_token: str | None = None
    meta_whatsapp_access_token: str | None = None
    meta_whatsapp_phone_number_id: str | None = None
    meta_send_handoff_ack: bool = True
    evolution_enabled: bool = True
    evolution_api_url: str = "http://127.0.0.1:8080"
    evolution_api_key: str | None = None
    evolution_instance_name: str = "escritorio"
    evolution_send_handoff_ack: bool = True

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
