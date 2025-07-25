"""Configuration parsing for claudespace."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

import yaml

from .exceptions import ConfigError

CloneStrategy = Literal["worktree", "shallow", "full"]


@dataclass
class EnvMapping:
    """Environment variable mapping for a service."""

    var: str
    replace_port: int | None = None
    replace_pattern: str | None = None
    replace_with: str | None = None


@dataclass
class ServiceConfig:
    """Configuration for a Docker service."""

    name: str
    env_vars: list[str]
    env_mappings: list[EnvMapping]


@dataclass
class SetupCommand:
    """A setup command to run."""

    name: str
    command: str
    wait_for: list[str] | None = None


@dataclass
class WorkspaceConfig:
    """Complete workspace configuration."""

    version: int
    git_url: str
    install_commands: list[SetupCommand]
    post_start_commands: list[SetupCommand]
    services: dict[str, ServiceConfig]
    env_files: list[str]
    branch: str = "main"
    clone_depth: int = 1
    clone_strategy: CloneStrategy = "worktree"


def load_config(config_path: Path) -> WorkspaceConfig:
    """Load and parse a .claudespace.yaml file."""
    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    with open(config_path) as f:
        data = yaml.safe_load(f)

    if not data:
        raise ConfigError("Configuration file is empty")

    if data.get("version") != 1:
        raise ConfigError(f"Unsupported config version: {data.get('version')}. Expected version 1.")

    # Parse setup section
    setup = data.get("setup", {})
    git_url = setup.get("git_url")
    if not git_url:
        raise ConfigError("setup.git_url is required in configuration")

    branch = setup.get("branch", "main")
    clone_depth = setup.get("clone_depth", 1)
    clone_strategy = setup.get("clone_strategy", "worktree")

    # Validate clone strategy
    if clone_strategy not in ["worktree", "shallow", "full"]:
        raise ConfigError(
            f"Invalid clone_strategy: {clone_strategy}. Must be 'worktree', 'shallow', or 'full'"
        )

    # Parse install commands
    install_commands: list[SetupCommand] = []
    for cmd in setup.get("install", []):
        install_commands.append(
            SetupCommand(name=cmd["name"], command=cmd["command"], wait_for=cmd.get("wait_for", []))
        )

    # Parse post-start commands
    post_start_commands: list[SetupCommand] = []
    for cmd in setup.get("post_start", []):
        post_start_commands.append(
            SetupCommand(name=cmd["name"], command=cmd["command"], wait_for=cmd.get("wait_for", []))
        )

    # Parse services
    services: dict[str, ServiceConfig] = {}
    for service_name, service_data in data.get("services", {}).items():
        # Simple format: just env_vars list
        if isinstance(service_data, dict) and "env_vars" in service_data:
            services[service_name] = ServiceConfig(
                name=service_name,
                env_vars=cast(list[str], service_data["env_vars"]),
                env_mappings=[],
            )
        # Advanced format: env_mappings
        elif isinstance(service_data, dict) and "env_mappings" in service_data:
            mappings: list[EnvMapping] = []
            for mapping in service_data["env_mappings"]:
                if isinstance(mapping, dict):
                    mappings.append(
                        EnvMapping(
                            var=str(mapping["var"]),
                            replace_port=int(mapping["replace_port"])
                            if mapping.get("replace_port") is not None
                            else None,
                            replace_pattern=str(mapping["replace_pattern"])
                            if mapping.get("replace_pattern") is not None
                            else None,
                            replace_with=str(mapping["replace_with"])
                            if mapping.get("replace_with") is not None
                            else None,
                        )
                    )
            services[service_name] = ServiceConfig(
                name=service_name,
                env_vars=[m.var for m in mappings],
                env_mappings=mappings,
            )

    # Parse env files
    env_files = data.get("env_files", [".env"])

    return WorkspaceConfig(
        version=1,
        git_url=git_url,
        install_commands=install_commands,
        post_start_commands=post_start_commands,
        services=services,
        env_files=env_files,
        branch=branch,
        clone_depth=clone_depth,
        clone_strategy=clone_strategy,
    )
