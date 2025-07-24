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

install: clean build
    uv tool uninstall claudespace
    uv tool install . --force