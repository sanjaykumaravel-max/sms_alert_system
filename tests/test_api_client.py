import pytest
from unittest.mock import AsyncMock, patch
from src.api_client import sync_get_machines, _bg_loop, _bg_thread

@pytest.fixture(autouse=True)
def cleanup_api_client_bg_loop():
    """Ensure the background loop gets closed after test if necessary."""
    yield
    # We do not explicitly kill the thread as it is a daemon thread,
    # but we could stop the loop if needed.

@patch('src.api_client.APIClient.get_machines', new_callable=AsyncMock)
def test_sync_get_machines_uses_background_loop(mock_get_machines):
    """Test that sync_get_machines successfully schedules onto the background loop."""
    # Arrange
    expected_data = [{'id': 1, 'name': 'Excavator'}]
    mock_get_machines.return_value = expected_data

    # Act
    result = sync_get_machines()

    # Assert
    assert result == expected_data
    mock_get_machines.assert_awaited_once()
    
    # Verify the thread was actually spun up
    from src.api_client import _bg_thread, _bg_loop
    assert _bg_thread is not None
    assert _bg_thread.is_alive()
    assert _bg_loop is not None
    assert _bg_loop.is_running()
