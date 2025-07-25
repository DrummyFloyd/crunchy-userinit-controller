import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Add src directory to path so we can import userinit
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Import the config module
from userinit import config


class TestEnvironmentConfiguration:
    """Test environment-specific configurations."""

    @patch.dict("os.environ", {"DEV_MODE": "true"})
    def test_dev_mode_enabled(self):
        # Test DEV_MODE environment variable parsing
        import importlib
        from userinit import config as config_module

        importlib.reload(config_module)
        assert config_module.DEV_MODE is True

    @patch.dict("os.environ", {"DEV_MODE": "false"})
    def test_dev_mode_disabled(self):
        # Test DEV_MODE disabled
        import importlib
        from userinit import config as config_module

        importlib.reload(config_module)
        assert config_module.DEV_MODE is False

    @patch.dict("os.environ", {"CRUI_WATCH_NAMESPACE": "custom-namespace"})
    def test_custom_watch_namespace(self):
        # Test custom watch namespace configuration
        import importlib
        from userinit import config as config_module

        importlib.reload(config_module)
        assert config_module.CRUI_WATCH_NAMESPACE == "custom-namespace"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
