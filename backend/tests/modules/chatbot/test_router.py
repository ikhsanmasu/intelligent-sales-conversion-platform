from unittest.mock import patch


def test_chat_endpoint_success(client):
    mock_result = {
        "response": "Halo! Ada yang bisa saya bantu?",
        "usage": {"prompt_tokens": 10, "completion_tokens": 8, "total_tokens": 18},
        "session_id": "test-session-123",
    }

    with patch("app.modules.chatbot.service.chat", return_value=mock_result) as mock_chat:
        response = client.post(
            "/v1/chatbot/chat",
            json={"message": "Halo"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["data"]["response"] == "Halo! Ada yang bisa saya bantu?"
    assert data["data"]["session_id"] == "test-session-123"
    assert "processing_time" in data


def test_chat_endpoint_with_session(client):
    mock_result = {
        "response": "Baik, ini lanjutannya.",
        "usage": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30},
        "session_id": "existing-session",
    }

    with patch("app.modules.chatbot.service.chat", return_value=mock_result):
        response = client.post(
            "/v1/chatbot/chat",
            json={
                "message": "Lanjutkan",
                "session_id": "existing-session",
            },
        )

    assert response.status_code == 200
    assert response.json()["data"]["session_id"] == "existing-session"


def test_chat_endpoint_with_history(client):
    mock_result = {
        "response": "Oke, saya ingat.",
        "usage": {"prompt_tokens": 25, "completion_tokens": 5, "total_tokens": 30},
        "session_id": "hist-session",
    }

    with patch("app.modules.chatbot.service.chat", return_value=mock_result):
        response = client.post(
            "/v1/chatbot/chat",
            json={
                "message": "Ingat ini",
                "history": [
                    {"role": "user", "content": "Halo"},
                    {"role": "assistant", "content": "Halo juga!"},
                ],
            },
        )

    assert response.status_code == 200
    assert response.json()["data"]["response"] == "Oke, saya ingat."


def test_get_history_empty(client):
    response = client.get("/v1/chatbot/history/nonexistent-session")
    assert response.status_code == 200
    assert response.json() == []


def test_delete_history(client):
    response = client.delete("/v1/chatbot/history/some-session")
    assert response.status_code == 200
    assert response.json()["status"] == "success"
