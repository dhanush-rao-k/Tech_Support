import json
import tempfile
import unittest
from pathlib import Path

from overlay_assistant import (
    Action,
    FrontendAgent,
    Step,
    _extract_json_blob,
    infer_task_key,
    load_task_library,
    suggest_tasks,
)


class OverlayAssistantTests(unittest.TestCase):
    def test_infer_task_key_scores_multiple_keywords(self):
        self.assertEqual(infer_task_key("my internet wifi is down"), "wifi")
        self.assertEqual(infer_task_key("need vpn secure access"), "vpn")
        self.assertIsNone(infer_task_key(""))

    def test_load_task_library_merges_tasks_file(self):
        payload = {
            "bluetooth": {
                "title": "Connect Bluetooth Device",
                "description": "Pair a bluetooth device",
                "steps": [{"instruction": "Open settings", "actions": [{"type": "open_app", "value": "settings"}]}],
            }
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            tasks_file = Path(tmpdir) / "tasks.json"
            tasks_file.write_text(json.dumps(payload), encoding="utf-8")

            tasks = load_task_library(str(tasks_file))

        self.assertIn("wifi", tasks)
        self.assertIn("bluetooth", tasks)
        self.assertEqual(tasks["bluetooth"].title, "Connect Bluetooth Device")
        self.assertEqual(tasks["bluetooth"].steps[0].actions[0].type, "open_app")

    def test_suggest_tasks_returns_ranked_matches(self):
        tasks = load_task_library("does-not-exist.json")
        suggestions = suggest_tasks("please connect vpn", tasks)
        self.assertEqual(suggestions[0], "vpn")

    def test_extract_json_blob_supports_fenced_json(self):
        blob = _extract_json_blob("```json\n{\"title\":\"x\",\"description\":\"y\",\"steps\":[]}\n```")
        self.assertIsNotNone(blob)
        self.assertEqual(blob["title"], "x")

    def test_agent_handles_unknown_action(self):
        agent = FrontendAgent()
        logs = agent.execute_step(Step(instruction="x", actions=[Action(type="unknown")]))
        self.assertIn("Unknown action type", logs[0])


if __name__ == "__main__":
    unittest.main()
