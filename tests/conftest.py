import os
import sys

# The app reads its config at import time; give it harmless values so the
# tests never need a real database, secret or OpenAI key. load_dotenv() does
# not override variables that are already set.
os.environ.setdefault("APP_SECRET_KEY", "test-secret-" + "x" * 32)
os.environ["DATABASE_URL"] = "postgresql://test:test@localhost:5432/test_unused"
os.environ.setdefault("OPENAI_API_KEY", "test-key")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
