from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from session_store import SessionRegistry


def in_memory_registry() -> SessionRegistry:
    return SessionRegistry(root=Path("."), db_path=":memory:")


class SessionRegistryTests(unittest.TestCase):
    def test_put_then_get_round_trips(self):
        registry = in_memory_registry()

        registry.put("abc", entry_id=5139814, horizon=3, risk_profile="stable")
        pointer = registry.get("abc")

        self.assertIsNotNone(pointer)
        self.assertEqual(pointer.entry_id, 5139814)
        self.assertEqual(pointer.horizon, 3)
        self.assertEqual(pointer.risk_profile, "stable")

    def test_get_missing_session_returns_none(self):
        registry = in_memory_registry()

        self.assertIsNone(registry.get("missing"))

    def test_put_upserts_existing_session(self):
        registry = in_memory_registry()

        registry.put("s1", entry_id=1, horizon=1, risk_profile="balanced")
        registry.put("s1", entry_id=1, horizon=5, risk_profile="upside")

        pointer = registry.get("s1")
        self.assertEqual(pointer.horizon, 5)
        self.assertEqual(pointer.risk_profile, "upside")


if __name__ == "__main__":
    unittest.main()
