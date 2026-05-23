from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient


def _ml_response(status: str, done: int = 5, total: int = 10, ticker: str = "AAPL") -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        "status": status,
        "job_id": "job-test",
        "done": done,
        "total": total,
        "current_ticker": ticker,
    }
    return resp


def _mock_http(*responses) -> AsyncMock:
    http = AsyncMock()
    http.get.side_effect = list(responses)
    return http


# ── 진행 중 메시지 스트리밍 ───────────────────────────────────

@patch("asyncio.sleep", new_callable=AsyncMock)
@patch("app.services.scanner.get_http_client")
def test_ws_streams_progress_then_complete(mock_get_http, _mock_sleep, client: TestClient) -> None:
    """running → completed 순서로 메시지가 순차 도착하고 연결이 정상 종료된다."""
    running = _ml_response("running", done=5, total=10)
    completed = _ml_response("completed", done=10, total=10, ticker="")
    mock_get_http.return_value = _mock_http(running, completed)

    with client.websocket_connect("/ws/scanner/job-test") as ws:
        msg1 = ws.receive_json()
        msg2 = ws.receive_json()

    assert msg1["type"] == "progress"
    assert msg1["job_id"] == "job-test"
    assert msg1["processed"] == 5
    assert msg1["total"] == 10
    assert msg1["ticker"] == "AAPL"

    assert msg2["type"] == "complete"
    assert msg2["message"] == "completed"


# ── 완료 즉시 종료 ────────────────────────────────────────────

@patch("asyncio.sleep", new_callable=AsyncMock)
@patch("app.services.scanner.get_http_client")
def test_ws_completed_sends_complete_and_closes(mock_get_http, _mock_sleep, client: TestClient) -> None:
    """첫 응답이 completed이면 단일 메시지 후 연결이 종료된다."""
    mock_get_http.return_value = _mock_http(_ml_response("completed", done=10, total=10))

    with client.websocket_connect("/ws/scanner/job-done") as ws:
        msg = ws.receive_json()

    assert msg["type"] == "complete"
    assert msg["message"] == "completed"


# ── 실패 상태 ────────────────────────────────────────────────

@patch("asyncio.sleep", new_callable=AsyncMock)
@patch("app.services.scanner.get_http_client")
def test_ws_failed_sends_error_type(mock_get_http, _mock_sleep, client: TestClient) -> None:
    """ML이 failed를 반환하면 type=error 메시지 후 연결이 종료된다."""
    mock_get_http.return_value = _mock_http(_ml_response("failed", done=3, total=10))

    with client.websocket_connect("/ws/scanner/job-fail") as ws:
        msg = ws.receive_json()

    assert msg["type"] == "error"
    assert msg["message"] == "failed"


# ── ML 비정상 상태코드 ────────────────────────────────────────

@patch("asyncio.sleep", new_callable=AsyncMock)
@patch("app.services.scanner.get_http_client")
def test_ws_ml_non_200_sends_error(mock_get_http, _mock_sleep, client: TestClient) -> None:
    """ML status 엔드포인트가 200이 아니면 type=error 메시지 후 종료된다."""
    bad_resp = MagicMock()
    bad_resp.status_code = 503
    mock_get_http.return_value = _mock_http(bad_resp)

    with client.websocket_connect("/ws/scanner/job-bad") as ws:
        msg = ws.receive_json()

    assert msg["type"] == "error"
    assert "503" in msg["message"]


# ── 네트워크 예외 ────────────────────────────────────────────

@patch("asyncio.sleep", new_callable=AsyncMock)
@patch("app.services.scanner.get_http_client")
def test_ws_network_exception_sends_error_and_closes(mock_get_http, _mock_sleep, client: TestClient) -> None:
    """ML 호출 중 예외 발생 시 type=error 메시지를 보내고 정상 종료한다."""
    http = AsyncMock()
    http.get.side_effect = Exception("network failure")
    mock_get_http.return_value = http

    with client.websocket_connect("/ws/scanner/job-err") as ws:
        msg = ws.receive_json()

    assert msg["type"] == "error"
    assert "network failure" in msg["message"]
