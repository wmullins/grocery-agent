from __future__ import annotations

import json
import os
import tomllib
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .safety import atomic_write_text, ensure_private_dir, ensure_private_file


class ConfigError(RuntimeError):
    pass


def app_home() -> Path:
    override = os.environ.get("GROCERY_AGENT_HOME")
    if override:
        return Path(override).expanduser()
    return Path.home() / "Library" / "Application Support" / "grocery-agent"


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_vault() -> Path:
    override = os.environ.get("GROCERY_AGENT_VAULT")
    if override:
        return Path(override).expanduser()
    sibling = project_root().parent / "Graham"
    if sibling.is_dir():
        return sibling
    known = Path.home() / "Library" / "CloudStorage" / "OneDrive-Personal" / "Documents" / "Graham" / "Graham"
    return known


def default_node_prefix() -> Path:
    return app_home() / "node"


class AgentSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    retailers: list[str] = Field(default_factory=lambda: ["sainsburys", "ocado"])
    budget_gbp: float = 70.0
    household_size: int = 2
    dietary_restrictions: list[str] = Field(default_factory=list)
    allergies: list[str] = Field(default_factory=list)
    postcode: str = ""
    fulfilment: str = "delivery"
    max_prep_minutes: int = 30
    leftovers: bool = True


class PathSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vault: Path = Field(default_factory=default_vault)
    output_folder: str = "10 Projects/Grocery Agent"

    @field_validator("vault", mode="before")
    @classmethod
    def expand_vault(cls, value: Any) -> Any:
        if isinstance(value, str):
            return Path(value).expanduser()
        return value


class RetailSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_prefix: Path = Field(default_factory=default_node_prefix)
    package: str = "open-supermarkets@3.0.0"
    timeout_seconds: int = 90
    price_ttl_minutes: int = 1440


class LlmSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = "ollama"
    model: str = "qwen3:4b-instruct-2507-q4_K_M"
    base_url: str = "http://127.0.0.1:11434"
    timeout_seconds: int = 120
    enabled: bool = True


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent: AgentSettings = Field(default_factory=AgentSettings)
    paths: PathSettings = Field(default_factory=PathSettings)
    retail: RetailSettings = Field(default_factory=RetailSettings)
    llm: LlmSettings = Field(default_factory=LlmSettings)


def config_file(home: Path | None = None) -> Path:
    return (home or app_home()) / "config.toml"


def database_file(home: Path | None = None) -> Path:
    return (home or app_home()) / "grocery.sqlite3"


def hmac_key_file(home: Path | None = None) -> Path:
    return (home or app_home()) / "order-id.key"


def load_config(home: Path | None = None) -> Config:
    path = config_file(home)
    if not path.exists():
        raise ConfigError(f"No config found at {path}. Run `grocery init` first.")
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    config = Config.model_validate(data)
    config.paths.vault = config.paths.vault.expanduser()
    config.retail.node_prefix = config.retail.node_prefix.expanduser()
    return config


def _toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, Path):
        value = str(value)
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(item) for item in value) + "]"
    raise ConfigError(f"Unsupported config value: {value!r}")


def render_config(config: Config) -> str:
    lines: list[str] = []
    for section_name in ("agent", "paths", "retail", "llm"):
        section = getattr(config, section_name)
        lines.append(f"[{section_name}]")
        for key, value in section.model_dump().items():
            lines.append(f"{key} = {_toml_value(value)}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def save_config(config: Config, home: Path | None = None) -> Path:
    root = ensure_private_dir(home or app_home())
    path = config_file(root)
    atomic_write_text(path, render_config(config))
    ensure_private_file(path)
    return path


def ensure_runtime_dirs(home: Path | None = None) -> None:
    root = ensure_private_dir(home or app_home())
    for name in ("cache", "logs", "exports"):
        ensure_private_dir(root / name)


def default_config() -> Config:
    return Config()


def config_summary(config: Config) -> dict[str, Any]:
    data = config.model_dump(mode="json")
    agent = data["agent"]
    if agent.get("postcode"):
        agent["postcode"] = "[set]"
    return data
