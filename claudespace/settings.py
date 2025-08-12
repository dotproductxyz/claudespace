"""Settings and configuration for claudespace."""

import os
import shutil


def get_claude_command() -> str:
    """Get the claude command to use.

    Checks in order:
    1. CLAUDESPACE_CLAUDE_COMMAND environment variable
    2. 'claude' in PATH
    3. Falls back to 'claude' string
    """
    # Check environment variable first
    env_command = os.environ.get("CLAUDESPACE_CLAUDE_COMMAND")
    if env_command:
        return env_command

    # Try to find claude in PATH
    claude_path = shutil.which("claude")
    if claude_path:
        return claude_path

    # Fallback to just 'claude' - will let subprocess handle the error
    return "claude"


CLAUDE_COMMAND = get_claude_command()
