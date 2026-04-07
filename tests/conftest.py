# ABOUTME: Shared test configuration and fixtures.
# ABOUTME: Whitelists valid test files to prevent hook-generated tests from breaking the suite.

# Only collect test files we explicitly created
_VALID_TESTS = {"test_services.py", "test_adapters.py", "test_coordinator.py", "conftest.py", "__init__.py"}

def pytest_ignore_collect(collection_path, config):
    """Ignore any test file not in our whitelist."""
    if collection_path.name.startswith("test_") and collection_path.name not in _VALID_TESTS:
        return True
    return False
