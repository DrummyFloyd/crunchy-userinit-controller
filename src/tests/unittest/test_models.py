import base64
import sys
from pathlib import Path

import kopf
import pytest

# Add src directory to path so we can import userinit
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Import the models module
from userinit.models import decode_value, PgUserSecret


class TestDecodeValue:
    """Test the decode_value utility function."""

    def test_decode_value_valid_base64(self):
        # Test with valid base64 encoded string
        encoded = base64.b64encode(b"test_value").decode("utf-8")
        result = decode_value(encoded)
        assert result == "test_value"

    def test_decode_value_none(self):
        # Test with None input
        result = decode_value(None)
        assert result is None

    def test_decode_value_empty_string(self):
        # Test with empty string
        result = decode_value("")
        assert result is None

    def test_decode_value_unicode(self):
        # Test with unicode characters
        unicode_text = "héllo wörld"
        encoded = base64.b64encode(unicode_text.encode("utf-8")).decode("utf-8")
        result = decode_value(encoded)
        assert result == unicode_text


class TestPgUserSecret:
    """Test the PgUserSecret class."""

    def test_from_k8s_secret_success(self, valid_secret_body):
        # Test successful creation from valid secret
        pguser_secret = PgUserSecret.from_k8s_secret(valid_secret_body)

        assert pguser_secret.secret_name == "test-cluster-pguser-testuser"
        assert pguser_secret.cluster_name == "test-cluster"
        assert pguser_secret.cluster_ns == "test-ns"
        assert pguser_secret.superuser == "postgres"
        assert pguser_secret.dbname == "testdb"
        assert pguser_secret.role_name == "testuser"

    def test_from_k8s_secret_missing_superuser_label(self, valid_secret_body):
        # Test when superuser label is missing
        del valid_secret_body.metadata.labels[
            "crunchy-userinit.ramblurr.github.com/superuser"
        ]

        with pytest.raises(kopf.TemporaryError, match="superuser label not found"):
            PgUserSecret.from_k8s_secret(valid_secret_body)

    def test_from_k8s_secret_missing_dbname(self, valid_secret_body):
        # Test when dbname is missing from secret data
        del valid_secret_body.data["dbname"]

        with pytest.raises(kopf.TemporaryError, match="Could not parse dbname"):
            PgUserSecret.from_k8s_secret(valid_secret_body)

    def test_from_k8s_secret_missing_user(self, valid_secret_body):
        # Test when user is missing from secret data
        del valid_secret_body.data["user"]

        with pytest.raises(kopf.TemporaryError, match="Could not parse role_name"):
            PgUserSecret.from_k8s_secret(valid_secret_body)

    def test_custom_secret_creation(self, mock_k8s_secret):
        # Example of using the mock_k8s_secret factory
        custom_secret = mock_k8s_secret(
            cluster_name="custom-cluster", username="customuser", dbname="customdb"
        )

        pguser_secret = PgUserSecret.from_k8s_secret(custom_secret)

        assert pguser_secret.secret_name == "custom-cluster-pguser-customuser"
        assert pguser_secret.role_name == "customuser"
        assert pguser_secret.dbname == "customdb"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
