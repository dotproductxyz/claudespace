"""Workspace management for claudespace."""

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .config import SetupCommand, WorkspaceConfig
from .docker_utils import DockerComposeManager
from .exceptions import ClaudespaceError, WorkspaceExistsError, WorkspaceNotFoundError


@dataclass
class Workspace:
    """Represents a Claude workspace."""

    name: str
    path: Path
    config: WorkspaceConfig | None

    def is_running(self) -> bool:
        """Check if Docker services are running."""
        compose = DockerComposeManager(self.path, f"claude_{self.name}")
        return compose.is_running()

    def start(self):
        """Start Docker services."""
        compose = DockerComposeManager(self.path, f"claude_{self.name}")
        compose.up()

    def stop(self):
        """Stop Docker services."""
        compose = DockerComposeManager(self.path, f"claude_{self.name}")
        compose.down()

    def destroy(self):
        """Destroy workspace and Docker resources."""
        compose = DockerComposeManager(self.path, f"claude_{self.name}")
        compose.down(volumes=True)
        if self.path.exists():
            shutil.rmtree(self.path)


class WorkspaceManager:
    """Manages Claude workspaces."""

    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def create_workspace(self, name: str, config: WorkspaceConfig) -> Workspace:
        """Create a new workspace."""
        workspace_path = self.base_dir / name

        if workspace_path.exists():
            raise WorkspaceExistsError(
                f"Workspace '{name}' already exists. Use 'claudespace attach {name}' to connect to it."
            )

        # Clone repository
        self._clone_repository(config, workspace_path)

        # Create Docker Compose override
        compose = DockerComposeManager(workspace_path, f"claude_{name}")
        compose.create_override(config.services)

        # Update environment files
        self._update_env_files(workspace_path, config, compose.port_mappings)

        # Run install commands
        self._run_commands(workspace_path, config.install_commands)

        # Start Docker services
        compose.up()

        # Run post-start commands
        self._run_commands(workspace_path, config.post_start_commands, compose)

        return Workspace(name, workspace_path, config)

    def get_workspace(self, name: str) -> Workspace:
        """Get an existing workspace."""
        workspace_path = self.base_dir / name
        if not workspace_path.exists():
            raise WorkspaceNotFoundError(
                f"Workspace '{name}' not found. Available workspaces: {', '.join(w.name for w in self.list_workspaces()) or 'none'}"
            )

        # TODO: Load config from workspace
        return Workspace(name, workspace_path, None)

    def list_workspaces(self) -> list[Workspace]:
        """List all workspaces."""
        workspaces: list[Workspace] = []
        if self.base_dir.exists():
            for path in self.base_dir.iterdir():
                if path.is_dir():
                    workspaces.append(Workspace(path.name, path, None))
        return workspaces

    def destroy_workspace(self, name: str):
        """Destroy a workspace."""
        workspace = self.get_workspace(name)
        workspace.destroy()

    def _clone_repository(self, config: WorkspaceConfig, dest: Path):
        """Clone the repository."""
        cmd = ["git", "clone"]
        if config.clone_depth > 0:
            cmd.extend(["--depth", str(config.clone_depth)])
        if config.branch != "main":
            cmd.extend(["-b", config.branch])
        cmd.extend([config.git_url, str(dest)])

        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.strip()
            if "Repository not found" in error_msg:
                raise ClaudespaceError(f"Repository not found: {config.git_url}") from e
            elif "Could not resolve host" in error_msg:
                raise ClaudespaceError(
                    "Cannot connect to git host. Check your internet connection."
                ) from e
            elif "Permission denied" in error_msg:
                raise ClaudespaceError(
                    f"Permission denied. Check your git credentials for: {config.git_url}"
                ) from e
            else:
                raise ClaudespaceError(f"Git clone failed: {error_msg}") from e

    def _update_env_files(
        self,
        workspace_path: Path,
        config: WorkspaceConfig,
        port_mappings: dict[str, tuple[int, int]],
    ):
        """Update environment files with new ports."""
        for env_file in config.env_files:
            env_path = workspace_path / env_file
            if not env_path.exists():
                # Create from example if it exists
                example_path = workspace_path / f"{env_file}.example"
                if example_path.exists():
                    shutil.copy(example_path, env_path)
                else:
                    continue

            # Read current content
            content = env_path.read_text()

            # Update ports for each service
            for service_name, service_config in config.services.items():
                if service_name not in port_mappings:
                    continue

                old_port, new_port = port_mappings[service_name]

                # Simple port replacement in env vars
                for var_name in service_config.env_vars:
                    # Replace port in lines that start with var_name
                    lines = content.splitlines()
                    for i, line in enumerate(lines):
                        if line.startswith(f"{var_name}="):
                            lines[i] = line.replace(f":{old_port}", f":{new_port}")
                            lines[i] = lines[i].replace(f"={old_port}", f"={new_port}")
                    content = "\n".join(lines)

            # Write updated content
            env_path.write_text(content)

    def _run_commands(
        self,
        workspace_path: Path,
        commands: list[SetupCommand],
        compose_manager: DockerComposeManager | None = None,
    ):
        """Run setup commands."""
        for cmd in commands:
            # Wait for services if specified
            if cmd.wait_for and compose_manager:
                for service in cmd.wait_for:
                    try:
                        compose_manager.wait_for_service(service)
                    except TimeoutError as e:
                        raise ClaudespaceError(f"Service '{service}' failed to start: {e}") from e

            # Run command
            try:
                subprocess.run(
                    cmd.command,
                    shell=True,
                    cwd=workspace_path,
                    check=True,
                    capture_output=True,
                    text=True,
                )
            except subprocess.CalledProcessError as e:
                raise ClaudespaceError(f"Command '{cmd.name}' failed: {e.stderr.strip()}") from e
