from .io.google import GoogleSheetsClient

# Backward-compatible alias for existing imports.
SheetsClient = GoogleSheetsClient

__all__ = ["SheetsClient", "GoogleSheetsClient"]
