"""
Supabase Client — Free Tier Database + Realtime
==================================================
Initializes the Supabase Python client using env vars.
Provides a singleton accessor for the entire backend.
"""

import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_client = None


def get_supabase():
    """Get or create the Supabase client singleton."""
    global _client
    if _client is None:
        try:
            from supabase import create_client, Client

            url = os.getenv("SUPABASE_URL", "")
            key = os.getenv("SUPABASE_SERVICE_KEY", "")

            if not url or not key:
                logger.warning(
                    "SUPABASE_URL or SUPABASE_SERVICE_KEY not set. "
                    "Supabase features will be unavailable."
                )
                return None

            _client = create_client(url, key)
            logger.info(f"Supabase client initialized: {url[:40]}...")
        except ImportError:
            logger.error("supabase package not installed. Run: pip install supabase")
            return None
        except Exception as e:
            logger.error(f"Failed to initialize Supabase client: {e}")
            return None
    return _client


def reset_client():
    """Reset the singleton (useful for testing)."""
    global _client
    _client = None
