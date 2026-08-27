import os

from pylens.compat import enable_legacy_protobuf


def test_enable_legacy_protobuf_sets_python_implementation(monkeypatch):
    monkeypatch.delenv("PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION", raising=False)
    enable_legacy_protobuf()
    assert os.environ["PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION"] == "python"
