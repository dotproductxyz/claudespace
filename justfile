# Install dependencies
deps:
    uv sync

# Install dev dependencies
deps-dev:
    uv sync --dev

# Run linting with ruff
lint:
    uv run ruff check . --fix
    uv run ruff format .

# Run type checking with ty
typecheck:
    uv run ty check

# Run both lint and typecheck
check: lint typecheck

# Build package
build:
    uv build

# Clean up generated files
clean:
    rm -rf dist/
    rm -rf .ruff_cache/
    find . -type d -name "__pycache__" -exec rm -rf {} +
    find . -type f -name "*.pyc" -delete

# Development mode - run a local instance
dev:
    uv run claudespace --help

# Uninstall claudespace
uninstall:
    -uv tool uninstall claudespace

# Install claudespace
install: uninstall clean build
    #!/bin/bash
    # Backup original
    cp pyproject.toml pyproject.toml.bak

    # Add timestamp to version
    timestamp=$(date +%s)
    sed -i "" "s/version = \"\([^\"]*\)\"/version = \"\1.dev$timestamp\"/" pyproject.toml

    # Build and install
    uv build
    uv tool install . --force

    # Restore original
    mv pyproject.toml.bak pyproject.toml
