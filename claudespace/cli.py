#!/usr/bin/env python3
"""Main CLI interface for claudespace."""

import os
import subprocess
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from .config import load_config
from .exceptions import ClaudespaceError, WorkspaceExistsError, WorkspaceNotFoundError
from .workspace import WorkspaceManager

console = Console()


@click.group()
@click.version_option()
def main():
    """Manage isolated Docker environments for Claude Code development."""
    pass


def find_config_file(explicit_path: str | None = None) -> Path | None:
    """Find config file in current directory or git root."""
    config_names = [".claudespace.yaml", ".claudespace.yml"]

    if explicit_path:
        config_path = Path(explicit_path)
        if config_path.exists():
            return config_path
        return None

    # Check current directory
    current_dir = Path.cwd()
    for config_name in config_names:
        config_path = current_dir / config_name
        if config_path.exists():
            return config_path

    # Check git root
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True
        )
        git_root = Path(result.stdout.strip())
        for config_name in config_names:
            config_path = git_root / config_name
            if config_path.exists():
                return config_path
    except subprocess.CalledProcessError:
        # Not in a git repository
        pass

    return None


@main.command()
@click.argument("name")
@click.option("--config", "-c", help="Path to config file")
@click.option("--base-dir", default="~/claudespaces", help="Base directory for workspaces")
def create(name: str, config: str | None, base_dir: str):
    """Create a new isolated workspace."""
    try:
        config_path = find_config_file(config)
        if not config_path:
            if config:
                console.print(f"[red]Error: Config file '{config}' not found[/red]")
            else:
                console.print(
                    "[red]Error: No .claudespace.yaml found in current directory or git root[/red]"
                )
                console.print(
                    "[dim]Create a .claudespace.yaml file or use -c to specify the path[/dim]"
                )
            return

        workspace_config = load_config(config_path)
        manager = WorkspaceManager(Path(base_dir).expanduser())

        with console.status(f"Creating workspace '{name}'..."):
            workspace = manager.create_workspace(name, workspace_config)

        console.print(f"[green]✓ Created workspace:[/green] {workspace.path}")
        console.print(f"[green]✓ Docker project:[/green] claude_{name}")
        console.print(f"[green]✓ Config loaded from:[/green] {config_path}")
        console.print("\n[bold]Next steps:[/bold]")
        console.print(f"  cd {workspace.path}")
        console.print("  claude-code")

    except WorkspaceExistsError as e:
        console.print(f"[yellow]{e}[/yellow]")
        raise click.Abort() from e
    except FileNotFoundError as e:
        console.print(f"[red]Error: {e}[/red]")
        console.print("[dim]Make sure you're in a project with .claudespace.yaml[/dim]")
        raise click.Abort() from e
    except ClaudespaceError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise click.Abort() from e
    except Exception as e:
        console.print(f"[red]Unexpected error: {e}[/red]")
        raise click.Abort() from e


@main.command(name="list")
@click.option("--base-dir", default="~/claudespaces", help="Base directory for workspaces")
def list_workspaces(base_dir: str):
    """List all workspaces."""
    manager = WorkspaceManager(Path(base_dir).expanduser())
    workspaces = manager.list_workspaces()

    if not workspaces:
        console.print("No workspaces found.")
        return

    table = Table(title="Claude Workspaces")
    table.add_column("Name", style="cyan")
    table.add_column("Path", style="dim")
    table.add_column("Status", style="green")

    for ws in workspaces:
        status = "🟢 Running" if ws.is_running() else "⚪ Stopped"
        table.add_row(ws.name, str(ws.path), status)

    console.print(table)


@main.command()
@click.argument("name")
@click.option("--base-dir", default="~/claudespaces", help="Base directory for workspaces")
@click.option("--force", "-f", is_flag=True, help="Force removal without confirmation")
def destroy(name: str, base_dir: str, force: bool):
    """Destroy a workspace and its Docker resources."""
    manager = WorkspaceManager(Path(base_dir).expanduser())

    if not force and not click.confirm(f"Are you sure you want to destroy workspace '{name}'?"):
        return

    try:
        with console.status(f"Destroying workspace '{name}'..."):
            manager.destroy_workspace(name)
        console.print(f"[green]✓ Destroyed workspace '{name}'[/green]")
    except WorkspaceNotFoundError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise click.Abort() from e
    except Exception as e:
        console.print(f"[red]Error destroying workspace: {e}[/red]")
        raise click.Abort() from e


@main.command()
@click.argument("name")
@click.option("--base-dir", default="~/claudespaces", help="Base directory for workspaces")
def stop(name: str, base_dir: str):
    """Stop a workspace's Docker services."""
    manager = WorkspaceManager(Path(base_dir).expanduser())

    try:
        workspace = manager.get_workspace(name)
        workspace.stop()
        console.print(f"[green]✓ Stopped workspace '{name}'[/green]")
    except WorkspaceNotFoundError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise click.Abort() from e
    except Exception as e:
        console.print(f"[red]Error stopping workspace: {e}[/red]")
        raise click.Abort() from e


@main.command()
@click.argument("name")
@click.option("--base-dir", default="~/claudespaces", help="Base directory for workspaces")
def start(name: str, base_dir: str):
    """Start a workspace's Docker services."""
    manager = WorkspaceManager(Path(base_dir).expanduser())

    try:
        workspace = manager.get_workspace(name)
        workspace.start()
        console.print(f"[green]✓ Started workspace '{name}'[/green]")
    except WorkspaceNotFoundError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise click.Abort() from e
    except Exception as e:
        console.print(f"[red]Error starting workspace: {e}[/red]")
        raise click.Abort() from e


@main.command()
@click.argument("name")
@click.option("--base-dir", default="~/claudespaces", help="Base directory for workspaces")
def attach(name: str, base_dir: str):
    """Attach to a Claude Code session in a workspace."""
    manager = WorkspaceManager(Path(base_dir).expanduser())

    try:
        workspace = manager.get_workspace(name)
        if not workspace.is_running():
            console.print(f"[yellow]Starting Docker services for '{name}'...[/yellow]")
            workspace.start()

        # Use workspace name as conversation ID for consistency
        conversation_id = f"claudespace-{name}"

        # Always use --resume with the conversation ID
        # Claude Code will create a new conversation if it doesn't exist
        cmd = ["claude-code", "--resume", conversation_id]

        console.print(f"[green]✓ Attaching to workspace '{name}'[/green]")
        console.print(f"[dim]Conversation ID: {conversation_id}[/dim]")

        # Change to workspace directory and run claude
        os.chdir(workspace.path)
        os.execvp("claude-code", cmd)

    except WorkspaceNotFoundError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise click.Abort() from e
    except FileNotFoundError:
        console.print("[red]Error: 'claude-code' command not found[/red]")
        console.print(
            "[dim]Please install Claude Code: https://docs.anthropic.com/claude-code[/dim]"
        )
        raise click.Abort() from None
    except Exception as e:
        console.print(f"[red]Error attaching to workspace: {e}[/red]")
        raise click.Abort() from e


@main.command()
@click.argument("name")
@click.option("--path", "-p", help="Subdirectory to open (e.g., './backend')")
@click.option("--base-dir", default="~/claudespaces", help="Base directory for workspaces")
def cursor(name: str, path: str | None, base_dir: str):
    """Open a workspace in Cursor IDE."""
    manager = WorkspaceManager(Path(base_dir).expanduser())

    try:
        workspace = manager.get_workspace(name)

        # Determine the directory to open
        if path:
            # Resolve the path relative to the workspace
            target_path = (workspace.path / path).resolve()

            # Ensure the path exists and is within the workspace
            if not target_path.exists():
                console.print(
                    f"[red]Error: Path '{path}' does not exist in workspace '{name}'[/red]"
                )
                raise click.Abort()

            if not str(target_path).startswith(str(workspace.path)):
                console.print(f"[red]Error: Path '{path}' is outside the workspace[/red]")
                raise click.Abort()
        else:
            target_path = workspace.path

        # Launch Cursor with the target path
        try:
            subprocess.run(["cursor", str(target_path)], check=True)
            console.print(f"[green]✓ Opened Cursor with:[/green] {target_path}")
        except FileNotFoundError:
            console.print("[red]Error: 'cursor' command not found[/red]")
            console.print("[dim]Please ensure Cursor is installed and available in your PATH[/dim]")
            console.print(
                "[dim]You can install the Cursor CLI from: Cursor > Install 'cursor' command[/dim]"
            )
            raise click.Abort() from None
        except subprocess.CalledProcessError as e:
            console.print(f"[red]Error launching Cursor: {e}[/red]")
            raise click.Abort() from e

    except WorkspaceNotFoundError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise click.Abort() from e


if __name__ == "__main__":
    main()
