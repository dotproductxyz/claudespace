# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

Build and development:
- `just deps` - Install dependencies using uv
- `just deps-dev` - Install dev dependencies
- `just lint` - Run ruff linting and formatting
- `just typecheck` - Run type checking with ty
- `just check` - Run both lint and typecheck
- `just build` - Build package
- `just install` - Install claudespace tool globally
- `just clean` - Clean generated files

## Architecture Overview

Claudespace is a Python CLI tool that creates isolated Docker environments for Claude Code development. The key components:

1. **CLI Interface** (`cli.py`): Click-based commands for workspace management
   - Finds config files in current dir or git root
   - Commands: create, start, stop, destroy, attach, cursor, push, list

2. **Workspace Manager** (`workspace.py`): Core logic for workspace operations
   - Creates workspaces using git worktrees (default) or clones
   - Manages Docker service port remapping (starting from port 15000)
   - Updates environment files with new ports
   - Integrates with Claude Code sessions
   - Handles worktree cleanup on destroy

3. **Docker Integration** (`docker_utils.py`): Docker Compose management
   - Remaps ports to avoid conflicts between workspaces
   - Handles service health checks
   - Manages docker-compose.yml modifications

4. **Configuration** (`config.py`): YAML-based project setup
   - Validates `.claudespace.yaml` configuration
   - Supports three clone strategies: worktree, shallow, full
   - Supports simple and advanced port mapping
   - Manages install and post-start commands

## Key Design Patterns

- **Git Worktrees**: Default strategy uses git worktrees for instant workspace creation
- **Port Isolation**: Each workspace gets unique ports (15000+) to avoid conflicts
- **Environment Updates**: Automatically updates .env files with remapped ports
- **Git Integration**: Creates branches named `claude-<workspace>` for changes
- **Session Persistence**: Claude Code conversations are tied to workspace names

## Testing

Currently no automated tests are configured. When adding tests:
- Place them in a `tests/` directory
- Use pytest as the test framework
- Run with `uv run pytest`