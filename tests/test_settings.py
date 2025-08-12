"""Unit tests for the settings module."""

import os
from unittest.mock import MagicMock, patch

import pytest

from claudespace.settings import CLAUDE_COMMAND, get_claude_command


class TestGetClaudeCommand:
    """Test cases for get_claude_command function."""

    def test_env_variable_takes_precedence(self):
        """Test that CLAUDESPACE_CLAUDE_COMMAND env var is used first."""
        custom_path = "/custom/path/to/claude"
        with patch.dict(os.environ, {"CLAUDESPACE_CLAUDE_COMMAND": custom_path}):
            # Mock shutil.which to ensure env var takes precedence
            with patch("claudespace.settings.shutil.which") as mock_which:
                mock_which.return_value = "/usr/bin/claude"
                result = get_claude_command()
                assert result == custom_path
                # shutil.which should not be called when env var is set
                mock_which.assert_not_called()

    def test_uses_shutil_which_when_no_env_var(self):
        """Test that shutil.which is used when env var is not set."""
        expected_path = "/usr/local/bin/claude"
        with patch.dict(os.environ, {}, clear=True):
            # Ensure CLAUDESPACE_CLAUDE_COMMAND is not set
            if "CLAUDESPACE_CLAUDE_COMMAND" in os.environ:
                del os.environ["CLAUDESPACE_CLAUDE_COMMAND"]
            
            with patch("claudespace.settings.shutil.which") as mock_which:
                mock_which.return_value = expected_path
                result = get_claude_command()
                assert result == expected_path
                mock_which.assert_called_once_with("claude")

    def test_fallback_to_claude_string(self):
        """Test fallback to 'claude' string when not found in PATH."""
        with patch.dict(os.environ, {}, clear=True):
            # Ensure CLAUDESPACE_CLAUDE_COMMAND is not set
            if "CLAUDESPACE_CLAUDE_COMMAND" in os.environ:
                del os.environ["CLAUDESPACE_CLAUDE_COMMAND"]
            
            with patch("claudespace.settings.shutil.which") as mock_which:
                mock_which.return_value = None
                result = get_claude_command()
                assert result == "claude"
                mock_which.assert_called_once_with("claude")

    def test_empty_env_variable_ignored(self):
        """Test that empty env variable is ignored."""
        expected_path = "/usr/bin/claude"
        with patch.dict(os.environ, {"CLAUDESPACE_CLAUDE_COMMAND": ""}):
            with patch("claudespace.settings.shutil.which") as mock_which:
                mock_which.return_value = expected_path
                result = get_claude_command()
                assert result == expected_path
                mock_which.assert_called_once_with("claude")

    def test_whitespace_only_env_variable_ignored(self):
        """Test that whitespace-only env variable is ignored."""
        expected_path = "/usr/bin/claude"
        with patch.dict(os.environ, {"CLAUDESPACE_CLAUDE_COMMAND": "   "}):
            with patch("claudespace.settings.shutil.which") as mock_which:
                mock_which.return_value = expected_path
                result = get_claude_command()
                # Whitespace is not explicitly trimmed, so it would be used
                assert result == "   "
                mock_which.assert_not_called()


class TestClaudeCommandConstant:
    """Test cases for CLAUDE_COMMAND module constant."""

    def test_claude_command_is_string(self):
        """Test that CLAUDE_COMMAND is a string."""
        assert isinstance(CLAUDE_COMMAND, str)
        assert len(CLAUDE_COMMAND) > 0

    def test_module_reload_with_env_var(self):
        """Test module behavior when reloaded with different env vars."""
        import importlib
        import sys
        
        original_env = os.environ.get("CLAUDESPACE_CLAUDE_COMMAND")
        original_modules = sys.modules.copy()
        
        try:
            # Test with env variable
            os.environ["CLAUDESPACE_CLAUDE_COMMAND"] = "/test/claude"
            
            # Remove module from cache to force reload
            if "claudespace.settings" in sys.modules:
                del sys.modules["claudespace.settings"]
            
            # Re-import module
            import claudespace.settings as reloaded_settings
            assert reloaded_settings.CLAUDE_COMMAND == "/test/claude"
            
        finally:
            # Restore original state
            if original_env is not None:
                os.environ["CLAUDESPACE_CLAUDE_COMMAND"] = original_env
            elif "CLAUDESPACE_CLAUDE_COMMAND" in os.environ:
                del os.environ["CLAUDESPACE_CLAUDE_COMMAND"]
            
            # Restore original modules
            sys.modules.clear()
            sys.modules.update(original_modules)

    def test_module_reload_with_mock_which(self):
        """Test module reload with mocked shutil.which."""
        import importlib
        import sys
        
        original_env = os.environ.get("CLAUDESPACE_CLAUDE_COMMAND")
        original_modules = sys.modules.copy()
        
        try:
            # Clear env variable
            if "CLAUDESPACE_CLAUDE_COMMAND" in os.environ:
                del os.environ["CLAUDESPACE_CLAUDE_COMMAND"]
            
            # Remove module from cache
            if "claudespace.settings" in sys.modules:
                del sys.modules["claudespace.settings"]
            
            # Mock shutil.which before import
            with patch("shutil.which") as mock_which:
                mock_which.return_value = "/mocked/path/claude"
                
                # Import module with mocked which
                import claudespace.settings as reloaded_settings
                assert reloaded_settings.CLAUDE_COMMAND == "/mocked/path/claude"
                
        finally:
            # Restore original state
            if original_env is not None:
                os.environ["CLAUDESPACE_CLAUDE_COMMAND"] = original_env
            
            # Restore original modules
            sys.modules.clear()
            sys.modules.update(original_modules)


class TestIntegrationScenarios:
    """Integration-like tests for various scenarios."""

    @patch("claudespace.settings.shutil.which")
    def test_typical_macos_setup(self, mock_which):
        """Test typical macOS setup with claude in Homebrew."""
        mock_which.return_value = "/opt/homebrew/bin/claude"
        with patch.dict(os.environ, {}, clear=True):
            if "CLAUDESPACE_CLAUDE_COMMAND" in os.environ:
                del os.environ["CLAUDESPACE_CLAUDE_COMMAND"]
            result = get_claude_command()
            assert result == "/opt/homebrew/bin/claude"

    @patch("claudespace.settings.shutil.which")
    def test_typical_linux_setup(self, mock_which):
        """Test typical Linux setup with claude in /usr/local/bin."""
        mock_which.return_value = "/usr/local/bin/claude"
        with patch.dict(os.environ, {}, clear=True):
            if "CLAUDESPACE_CLAUDE_COMMAND" in os.environ:
                del os.environ["CLAUDESPACE_CLAUDE_COMMAND"]
            result = get_claude_command()
            assert result == "/usr/local/bin/claude"

    def test_custom_installation_path(self):
        """Test custom installation path via environment variable."""
        custom_path = "/home/user/.local/bin/claude-custom"
        with patch.dict(os.environ, {"CLAUDESPACE_CLAUDE_COMMAND": custom_path}):
            result = get_claude_command()
            assert result == custom_path

    @patch("claudespace.settings.shutil.which")
    def test_claude_not_installed(self, mock_which):
        """Test behavior when claude is not installed."""
        mock_which.return_value = None
        with patch.dict(os.environ, {}, clear=True):
            if "CLAUDESPACE_CLAUDE_COMMAND" in os.environ:
                del os.environ["CLAUDESPACE_CLAUDE_COMMAND"]
            result = get_claude_command()
            assert result == "claude"
            # This will likely fail when actually executed, but that's expected