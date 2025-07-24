# Claudespace

Isolated Docker environments for Claude Code development. This tool allows you to create separate development environments where Claude Code can work without affecting your main development setup.

## Features

- 🔧 **Isolated Environments**: Each workspace gets its own Docker services with unique ports
- 🚀 **Fast Setup**: Shallow clones and automated dependency installation
- 🐳 **Docker Integration**: Automatically remaps ports to avoid conflicts
- 📝 **Configuration-Driven**: Simple YAML configuration for project setup
- 🔄 **Environment Updates**: Automatically updates `.env` files with new ports

## Installation

```bash
# Install via just
just install
```

## Quick Start

1. Create a `.claudespace.yaml` in your project root:

```yaml
version: 1

setup:
  git_url: "https://github.com/yourcompany/yourproject.git"
  branch: "main"
  clone_depth: 1  # Shallow clone for speed
  
  install:
    - name: "Install backend dependencies"
      command: "cd backend && pip install -r requirements.txt"
    - name: "Install frontend dependencies"
      command: "cd frontend && npm install"
    
  post_start:
    - name: "Run database migrations"
      command: "python manage.py migrate"
      wait_for: ["db"]

services:
  db:
    env_vars: [DATABASE_URL, DB_HOST, DB_PORT]
  redis:
    env_vars: [REDIS_URL, CACHE_URL]

env_files:
  - .env
  - backend/.env
```

2. Create a new workspace from anywhere in your project:

```bash
# From project root or any subdirectory
claudespace create feature-x

# Or specify config path explicitly
claudespace create feature-x -c /path/to/.claudespace.yaml
```

The tool will look for `.claudespace.yaml` in:
- Current directory
- Git repository root (if you're in a git repo)

3. Attach to Claude Code in the workspace:

```bash
# Attach to the workspace (creates or resumes session automatically)
claudespace attach feature-x
```

## Commands

- `claudespace list` - List all workspaces
- `claudespace create <name>` - Create a new workspace
- `claudespace start <name>` - Start a workspace's Docker services
- `claudespace stop <name>` - Stop a workspace's Docker services
- `claudespace destroy <name>` - Remove a workspace and its resources
- `claudespace attach <name>` - Attach to Claude Code session in a workspace
- `claudespace cursor <name>` - Open workspace in Cursor IDE
- `claudespace push <name> <message>` - Push changes to branch `claude-<name>`

## Configuration

### Setup Section

- `git_url` (required): Repository to clone
- `branch`: Branch to checkout (default: "main")
- `clone_depth`: Git clone depth, 0 for full history (default: 1)
- `install`: Commands to run after cloning
- `post_start`: Commands to run after Docker services start

### Services Section

Map Docker Compose services to their environment variables. Only services listed here will have their ports remapped:

```yaml
services:
  postgres:
    env_vars: [DATABASE_URL, POSTGRES_HOST]
  redis:
    env_vars: [REDIS_URL, CACHE_HOST]
```

**Note**: Services not listed in the configuration will keep their original ports. To avoid conflicts when running multiple workspaces, make sure to include all services that expose ports.

### Advanced Port Mapping

For complex cases, use explicit port mapping:

```yaml
services:
  db:
    env_mappings:
      - var: DATABASE_URL
        replace_port: 5432
      - var: DB_PORT
        replace_value: "5432"
```

## How It Works

1. **Clone**: Creates a fresh clone of your repository
2. **Isolate**: Generates unique ports for Docker services (starting from port 15000)
3. **Configure**: Updates environment files with new ports
4. **Initialize**: Runs your install commands
5. **Launch**: Starts Docker services with the new configuration and create a Claude Code session
6. **Ready**: Claude Code can now work in the isolated environment

## Claude Code Integration

Each workspace maintains a persistent conversation tied to its name. The `attach` command automatically resumes your workspace conversation:

```bash
# Attach to a workspace
claudespace attach feature-x
```

## Cursor IDE Integration

Open any workspace in Cursor IDE:

```bash
# Open entire workspace
claudespace cursor feature-x

# Open specific subdirectory
claudespace cursor feature-x --path ./backend

# Or use short form
claudespace cursor feature-x -p frontend
```

## Example Workflow

```bash
# You're working on a feature
cd ~/myproject

# Create isolated environment for Claude
claudespace create new-feature

# Attach to Claude (creates new conversation)
claudespace attach new-feature

# Later, attach again (resumes existing conversation)
claudespace attach new-feature

# When Claude is done, push changes to a branch
claudespace push new-feature "Implement feature X with Claude's help"

# The changes are now on branch 'claude-new-feature'
# You can create a PR from this branch

# Clean up
claudespace destroy new-feature
```

## Requirements

- Python 3.13+
- Docker and Docker Compose
- Git

## Known Limitations

**Large Repository Performance**: Claudespace currently creates a shallow clone of your git repository for each workspace. While this works well for most projects, it may be slow and consume significant disk space for very large repositories. Future versions may use [git worktrees](https://git-scm.com/docs/git-worktree) as an alternative approach for better performance.

## About This Project

This project was vide coded with Claude Code. It's designed to solve the specific workflow needs at [Operator](https://operator.xyz), but you're encouraged to fork and adapt it to match your own development setup and requirements.

## License

Beerware 🍺
