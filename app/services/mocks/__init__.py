"""Mock implementations of external services for testing and development.

When ``MOCK_SERVICES=true`` is set in the environment (or ``.env``), the
application loads these fakes instead of hitting real Gmail / Telegram APIs.

Each mock records every call so tests can inspect what happened without any
network I/O.
"""
