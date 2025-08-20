"""Workspace management for claudespace."""

import contextlib
import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from rich.console import Console

from .config import SetupCommand, WorkspaceConfig
from .docker_utils import DockerComposeManager
from .exceptions import ClaudespaceError, WorkspaceExistsError, WorkspaceNotFoundError

console = Console()


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
        console.print("[dim]Stopping Docker services and removing volumes...[/dim]")
        compose = DockerComposeManager(self.path, f"claude_{self.name}")
        compose.down(volumes=True)

        # Check if this is a worktree
        is_worktree = False
        if self.path.exists():
            git_file = self.path / ".git"
            # .git is a file in worktrees, not a directory
            is_worktree = git_file.exists() and git_file.is_file()

        if is_worktree:
            console.print(f"[dim]Removing git worktree: {self.path}[/dim]")
            # Remove the worktree
            subprocess.run(
                ["git", "worktree", "remove", str(self.path), "--force"],
                capture_output=True,
                text=True,
            )
            # Also remove the branch
            branch_name = f"claude-{self.name}"
            console.print(f"[dim]Removing branch: {branch_name}[/dim]")
            subprocess.run(["git", "branch", "-D", branch_name], capture_output=True, text=True)
        elif self.path.exists():
            console.print(f"[dim]Removing workspace directory: {self.path}[/dim]")
            shutil.rmtree(self.path)


class WorkspaceManager:
    """Manages Claude workspaces."""

    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)
        # Store sessions in a JSON file in the base directory
        self.sessions_file = self.base_dir / ".claudespace-sessions.json"
        self._load_sessions()

    def create_workspace(
        self, name: str, config: WorkspaceConfig, config_path: Path, verbose: bool = False
    ) -> Workspace:
        """Create a new workspace."""
        workspace_path = self.base_dir / name

        if workspace_path.exists():
            raise WorkspaceExistsError(
                f"Workspace '{name}' already exists. Use 'claudespace attach {name}' to connect to it."
            )

        # Track resources created for cleanup on failure
        resources_created = {
            "workspace_dir": False,
            "git_worktree": False,
            "docker_started": False,
            "session_created": False,
        }

        try:
            # Set up repository based on clone strategy
            if config.clone_strategy == "worktree":
                console.print(f"[dim]Creating git worktree at {workspace_path}...[/dim]")
                self._setup_worktree(config, workspace_path, name, verbose)
                resources_created["git_worktree"] = True
                resources_created["workspace_dir"] = True
            else:
                clone_type = "shallow" if config.clone_strategy == "shallow" else "full"
                console.print(
                    f"[dim]Cloning repository ({clone_type}) from {config.git_url}...[/dim]"
                )
                self._clone_repository(config, workspace_path, name, verbose)
                resources_created["workspace_dir"] = True

            # Copy env files from root directory to workspace
            root_dir = config_path.parent
            self._copy_env_files(root_dir, workspace_path, config.env_files)

            # Create Docker Compose with remapped ports
            console.print("[dim]Creating Docker Compose with unique ports...[/dim]")
            compose = DockerComposeManager(workspace_path, f"claude_{name}")
            compose.create_remapped_compose(config.services)

            # Update environment files
            if config.env_files:
                console.print(
                    f"[dim]Updating environment files: {', '.join(config.env_files)}[/dim]"
                )
            self._update_env_files(workspace_path, config, compose.port_mappings)

            # Run install commands
            if config.install_commands:
                console.print(
                    f"[dim]Running {len(config.install_commands)} install command(s)...[/dim]"
                )
            self._run_commands(workspace_path, config.install_commands, verbose=verbose)

            # Start Docker services
            console.print("[dim]Starting Docker services...[/dim]")
            compose.up()
            resources_created["docker_started"] = True

            # Run post-start commands
            if config.post_start_commands:
                console.print(
                    f"[dim]Running {len(config.post_start_commands)} post-start command(s)...[/dim]"
                )
            self._run_commands(workspace_path, config.post_start_commands, compose, verbose=verbose)

            # Start a Claude session for this workspace
            console.print("[dim]Initializing Claude session...[/dim]")
            session_id = self.start_claude_session(workspace_path, config)
            if session_id:
                self.set_session_id(name, session_id)
                resources_created["session_created"] = True

            return Workspace(name, workspace_path, config)

        except Exception:
            # Clean up any resources that were created
            console.print("[yellow]Cleaning up resources...[/yellow]")
            self._cleanup_failed_workspace(name, workspace_path, resources_created, verbose)
            raise

    def get_workspace(self, name: str) -> Workspace:
        """Get an existing workspace."""
        workspace_path = self.base_dir / name
        if not workspace_path.exists():
            workspaces = self.list_workspaces()
            if workspaces:
                raise WorkspaceNotFoundError(
                    f"Workspace '{name}' not found. Available workspaces: {', '.join(w.name for w in workspaces)}"
                )
            else:
                raise WorkspaceNotFoundError(f"Workspace '{name}' not found")

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

        # Remove the session ID for this workspace
        if name in self.sessions:
            console.print(f"[dim]Removing Claude session for workspace '{name}'[/dim]")
            del self.sessions[name]
            self._save_sessions()

    def _clone_repository(
        self, config: WorkspaceConfig, dest: Path, workspace_name: str, verbose: bool = False
    ):
        """Clone the repository and create a feature branch."""
        cmd = ["git", "clone"]
        # Only add depth for shallow clones
        if config.clone_strategy == "shallow":
            cmd.extend(["--depth", "1"])
        if config.branch != "main":
            cmd.extend(["-b", config.branch])
        cmd.extend([config.git_url, str(dest)])

        try:
            if verbose:
                subprocess.run(cmd, check=True, text=True)
            else:
                subprocess.run(cmd, check=True, capture_output=True, text=True)

            # Create and checkout feature branch after cloning
            branch_name = f"claude-{workspace_name}"
            checkout_cmd = ["git", "checkout", "-b", branch_name]
            if verbose:
                subprocess.run(checkout_cmd, cwd=dest, check=True, text=True)
            else:
                subprocess.run(checkout_cmd, cwd=dest, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.strip() if not verbose else f"Exit code {e.returncode}"
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

    def _setup_worktree(
        self, config: WorkspaceConfig, dest: Path, workspace_name: str, verbose: bool = False
    ):
        """Create a git worktree instead of cloning."""
        # Check if we're in a git repository
        try:
            subprocess.run(
                ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True
            )
        except subprocess.CalledProcessError as e:
            raise ClaudespaceError(
                "Not in a git repository. Use 'clone_strategy: shallow' or 'clone_strategy: full' instead of 'worktree'."
            ) from e

        # Create worktree with a new branch from the configured base branch
        branch_name = f"claude-{workspace_name}"
        base_branch = config.branch  # This defaults to "main" in the config
        cmd = ["git", "worktree", "add", "-b", branch_name, str(dest), base_branch]

        try:
            if verbose:
                subprocess.run(cmd, check=True, text=True)
            else:
                subprocess.run(cmd, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.strip() if not verbose else f"Exit code {e.returncode}"
            if "already exists" in error_msg:
                raise ClaudespaceError(
                    f"Branch '{branch_name}' already exists. Remove it first with: git branch -D {branch_name}"
                ) from e
            else:
                raise ClaudespaceError(f"Failed to create worktree: {error_msg}") from e

    def _copy_env_files(self, root_dir: Path, workspace_path: Path, env_files: list[str]):
        """Copy env files from the root directory to the workspace."""
        for env_file in env_files:
            src_path = root_dir / env_file
            dest_path = workspace_path / env_file

            if src_path.exists():
                console.print(f"[dim]Copying {env_file} to workspace...[/dim]")
                # Create parent directories if needed
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_path, dest_path)
            else:
                raise ClaudespaceError(
                    f"Environment file '{env_file}' not found in {root_dir}. "
                    f"Please create the file before creating a workspace."
                )

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
        verbose: bool = False,
    ):
        """Run setup commands."""
        for cmd in commands:
            # Wait for services if specified
            if cmd.wait_for and compose_manager:
                for service in cmd.wait_for:
                    console.print(f"  [dim]Waiting for service '{service}' to be healthy...[/dim]")
                    try:
                        compose_manager.wait_for_service(service)
                    except TimeoutError as e:
                        raise ClaudespaceError(f"Service '{service}' failed to start: {e}") from e

            # Run command
            console.print(f"  [dim]Running: {cmd.name}[/dim]")
            if verbose:
                console.print(f"    [dim]Command: {cmd.command}[/dim]")

            # Get user's default shell
            user_shell = os.environ.get("SHELL", "/bin/bash")

            # Use -ic for interactive shell to ensure .zshrc/.bashrc is loaded
            # This is what your terminal does and why nvm works there
            shell_cmd = [user_shell, "-ic", cmd.command]

            try:
                if verbose:
                    # Show command output in verbose mode
                    result = subprocess.run(
                        shell_cmd,
                        cwd=workspace_path,
                        text=True,
                        env={**os.environ, "PWD": str(workspace_path)},
                    )
                    if result.returncode != 0:
                        raise subprocess.CalledProcessError(result.returncode, cmd.command)
                else:
                    # Capture output in non-verbose mode
                    subprocess.run(
                        shell_cmd,
                        cwd=workspace_path,
                        check=True,
                        capture_output=True,
                        text=True,
                        env={**os.environ, "PWD": str(workspace_path)},
                    )
            except subprocess.CalledProcessError as e:
                if verbose:
                    raise ClaudespaceError(
                        f"Command '{cmd.name}' failed with exit code {e.returncode}"
                    ) from e
                else:
                    raise ClaudespaceError(
                        f"Command '{cmd.name}' failed: {e.stderr.strip()}"
                    ) from e

    def _load_sessions(self):
        """Load sessions from file."""
        if self.sessions_file.exists():
            with open(self.sessions_file) as f:
                self.sessions = json.load(f)
        else:
            self.sessions = {}

    def _save_sessions(self):
        """Save sessions to file."""
        with open(self.sessions_file, "w") as f:
            json.dump(self.sessions, f, indent=2)

    def get_session_id(self, workspace_name: str) -> str | None:
        """Get the Claude session ID for a workspace."""
        return self.sessions.get(workspace_name)

    def set_session_id(self, workspace_name: str, session_id: str):
        """Set the Claude session ID for a workspace."""
        self.sessions[workspace_name] = session_id
        self._save_sessions()

    def start_claude_session(self, workspace_path: Path, config: WorkspaceConfig) -> str | None:
        """Start a new Claude session and return the session ID."""
        try:
            # Run claude with a simple prompt to get a session started
            result = subprocess.run(
                [
                    *config.claude_command_parts,
                    "--print",
                    "--output-format",
                    "json",
                    "Hello!",
                ],
                cwd=workspace_path,
                capture_output=True,
                text=True,
                check=True,
            )

            # Parse the JSON response to get the session ID
            response = json.loads(result.stdout)
            session_id = response.get("session_id")

            if session_id:
                console.print(f"[dim]Created Claude session: {session_id}[/dim]")

            return session_id
        except (subprocess.CalledProcessError, json.JSONDecodeError, KeyError) as e:
            console.print(f"[yellow]Warning: Could not create Claude session: {e}[/yellow]")
            return None

    def _cleanup_failed_workspace(
        self,
        name: str,
        workspace_path: Path,
        resources_created: dict[str, bool],
        verbose: bool = False,
    ):
        """Clean up resources after a failed workspace creation."""
        # Clean up session if created
        if resources_created.get("session_created") and name in self.sessions:
            console.print("[dim]Removing Claude session...[/dim]")
            del self.sessions[name]
            self._save_sessions()

        # Stop Docker services if started
        if resources_created.get("docker_started"):
            console.print("[dim]Stopping Docker services...[/dim]")
            try:
                compose = DockerComposeManager(workspace_path, f"claude_{name}")
                compose.down(volumes=True)
            except Exception as e:
                console.print(f"[yellow]Warning: Failed to stop Docker services: {e}[/yellow]")

        # Clean up workspace directory and git resources
        if resources_created.get("workspace_dir") and workspace_path.exists():
            if resources_created.get("git_worktree"):
                # This is a worktree, remove it properly
                console.print("[dim]Removing git worktree...[/dim]")
                try:
                    subprocess.run(
                        ["git", "worktree", "remove", str(workspace_path), "--force"],
                        capture_output=True,
                        text=True,
                        check=True,
                    )
                except subprocess.CalledProcessError as e:
                    console.print(f"[yellow]Warning: Failed to remove worktree: {e}[/yellow]")
                    # Try to remove directory anyway
                    with contextlib.suppress(Exception):
                        shutil.rmtree(workspace_path)

                # Remove the branch
                branch_name = f"claude-{name}"
                console.print(f"[dim]Removing branch: {branch_name}[/dim]")
                try:
                    subprocess.run(
                        ["git", "branch", "-D", branch_name],
                        capture_output=True,
                        text=True,
                        check=True,
                    )
                except subprocess.CalledProcessError as e:
                    console.print(f"[yellow]Warning: Failed to remove branch: {e}[/yellow]")
            else:
                # Regular directory, just remove it
                console.print("[dim]Removing workspace directory...[/dim]")
                try:
                    shutil.rmtree(workspace_path)
                except Exception as e:
                    console.print(f"[yellow]Warning: Failed to remove directory: {e}[/yellow]")

        console.print("[green]Cleanup completed[/green]")
