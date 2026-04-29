"""
Configuration management for the Ishikawa Knowledge System.
Loads settings from YAML config files and environment variables.
"""

import os
import yaml
from pathlib import Path
from typing import Dict, Any
from dataclasses import dataclass
from urllib.parse import urlparse

try:
    from dotenv import load_dotenv as _load_dotenv
except Exception:
    _load_dotenv = None


@dataclass
class DatabaseConfig:
    """Neo4j database configuration."""
    uri: str
    username: str
    password: str
    database: str = None
    host: str = "localhost"
    port: int = 7687
    max_connection_lifetime: int = 3600
    max_connection_pool_size: int = 50
    connection_acquisition_timeout: float = 60.0


@dataclass
class LLMConfig:
    """LLM (Ollama) configuration."""
    base_url: str
    model: str
    timeout: int
    max_retries: int = 3
    num_gpu: int = -1        # -1 = offload all layers to GPU; 0 = CPU only
    num_thread: int = 0      # 0 = auto-detect CPU threads


@dataclass
class APIConfig:
    """API server configuration."""
    host: str
    port: int
    cors_origins: list[str]


@dataclass
class AppConfig:
    """Main application configuration."""
    database: DatabaseConfig
    llm: LLMConfig
    api: APIConfig
    debug: bool = False
    log_level: str = "INFO"


def _load_env_file() -> None:
    """Load project .env into process env without overriding existing values."""
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if not env_path.exists():
        return

    # Prefer python-dotenv when available.
    if _load_dotenv is not None:
        _load_dotenv(env_path, override=True)  # Always override so .env is authoritative
        return

    # Lightweight fallback parser when python-dotenv is not installed.
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def load_config(config_path: str = "config/config.yaml") -> AppConfig:
    """
    Load configuration from YAML file and environment variables.

    Args:
        config_path: Path to the YAML configuration file

    Returns:
        AppConfig: Parsed configuration object
    """
    _load_env_file()
    config_file = Path(config_path)

    # Load YAML config
    if config_file.exists():
        with open(config_file, 'r', encoding='utf-8') as f:
            yaml_config = yaml.safe_load(f)
    else:
        yaml_config = {}

    neo4j_uri = os.getenv('NEO4J_URI', yaml_config.get('neo4j', {}).get('uri', 'bolt://localhost:7687'))
    parsed_neo4j = urlparse(neo4j_uri)

    # Override with environment variables
    env_config = {
        'neo4j': {
            'uri': neo4j_uri,
            'username': os.getenv('NEO4J_USERNAME', yaml_config.get('neo4j', {}).get('username', 'neo4j')),
            'password': os.getenv('NEO4J_PASSWORD', yaml_config.get('neo4j', {}).get('password', 'password')),
            'database': os.getenv('NEO4J_DATABASE', yaml_config.get('neo4j', {}).get('database', None)),
            'host': os.getenv('NEO4J_HOST', yaml_config.get('neo4j', {}).get('host', parsed_neo4j.hostname or 'localhost')),
            'port': int(os.getenv('NEO4J_PORT', yaml_config.get('neo4j', {}).get('port', parsed_neo4j.port or 7687))),
        },
        'ollama': {
            'base_url': os.getenv('OLLAMA_BASE_URL', yaml_config.get('ollama', {}).get('base_url', 'http://127.0.0.1:11434')),
            'model': os.getenv('OLLAMA_MODEL', yaml_config.get('ollama', {}).get('model', 'mistral')),
            'timeout': int(os.getenv('OLLAMA_TIMEOUT', yaml_config.get('ollama', {}).get('timeout', 900))),
            'num_gpu': int(os.getenv('OLLAMA_NUM_GPU', yaml_config.get('ollama', {}).get('num_gpu', -1))),
            'num_thread': int(os.getenv('OLLAMA_NUM_THREAD', yaml_config.get('ollama', {}).get('num_thread', 0))),
        },
        'api': {
            'host': os.getenv('API_HOST', yaml_config.get('api', {}).get('host', '0.0.0.0')),
            'port': int(os.getenv('API_PORT', yaml_config.get('api', {}).get('port', 8000))),
            'cors_origins': yaml_config.get('api', {}).get('cors_origins', ['*']),
        }
    }

    # Create config objects
    database_config = DatabaseConfig(**env_config['neo4j'])
    llm_config = LLMConfig(**env_config['ollama'])
    api_config = APIConfig(**env_config['api'])

    return AppConfig(
        database=database_config,
        llm=llm_config,
        api=api_config,
        debug=os.getenv('DEBUG', 'false').lower() == 'true',
        log_level=os.getenv('LOG_LEVEL', 'INFO')
    )


# Global config instance
_config: AppConfig = None


def get_config() -> AppConfig:
    """Get the global configuration instance."""
    global _config
    if _config is None:
        _config = load_config()
    return _config