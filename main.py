"""Root auto-detect fallback for Vercel (main:app). Prefer api.index:app."""
from api.index import app  # noqa: F401
