"""Expose the evidence API through the pipeline package entry point."""
try:
    from main import app as app
except ImportError:
    from backend.main import app as app
