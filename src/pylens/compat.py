from __future__ import annotations

import os


def enable_legacy_protobuf() -> None:
    """
    Force protobuf to use the Python implementation instead of the C++ implementation.

    This is a workaround for compatibility issues with certain protobuf versions
    and Python versions. The pure Python implementation is slower but more compatible.
    """
    os.environ["PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION"] = "python"