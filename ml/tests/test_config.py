"""app/core/config.py 단위 테스트"""

import sys
from unittest.mock import MagicMock, patch


def test_get_torch_device_returns_cpu_when_device_is_cpu() -> None:
    """lstm_device=cpu이면 torch import 없이 바로 cpu를 반환한다."""
    from app.core.config import get_torch_device

    with patch("app.core.config.settings") as mock_settings:
        mock_settings.lstm_device = "cpu"
        assert get_torch_device() == "cpu"


def test_get_torch_device_returns_cpu_when_torch_unavailable() -> None:
    """torch import 실패 시 cpu를 반환한다."""
    from app.core.config import get_torch_device

    with patch("app.core.config.settings") as mock_settings:
        mock_settings.lstm_device = "cuda"
        with patch.dict(sys.modules, {"torch": None}):
            assert get_torch_device() == "cpu"


def test_get_torch_device_returns_cuda_when_available() -> None:
    """torch.cuda.is_available()=True이면 cuda를 반환한다."""
    from app.core.config import get_torch_device

    mock_torch = MagicMock()
    mock_torch.cuda.is_available.return_value = True

    with patch("app.core.config.settings") as mock_settings:
        mock_settings.lstm_device = "cuda"
        with patch.dict(sys.modules, {"torch": mock_torch}):
            assert get_torch_device() == "cuda"


def test_get_torch_device_returns_cpu_when_cuda_unavailable() -> None:
    """torch는 있지만 CUDA 없으면 cpu를 반환한다."""
    from app.core.config import get_torch_device

    mock_torch = MagicMock()
    mock_torch.cuda.is_available.return_value = False

    with patch("app.core.config.settings") as mock_settings:
        mock_settings.lstm_device = "cuda"
        with patch.dict(sys.modules, {"torch": mock_torch}):
            assert get_torch_device() == "cpu"
