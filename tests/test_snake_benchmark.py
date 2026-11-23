import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from canvasgate import snake_benchmark as snake
from canvasgate.backends import MockBackend
from canvasgate.canvasgate import CanvasGateWorkflow


class CapturingMock(MockBackend):
    def __init__(self):
        super().__init__({"status": True, "confidence": 1, "text": "export const states = [];"})
        self.inputs = []

    def generate(self, instruction, context, feedback):
        self.inputs.append(context)
        return super().generate(instruction, context, feedback)


class SnakeBenchmarkTests(unittest.TestCase):
    def test_gates_preserve_all_animation_and_contract_requirements(self):
        with tempfile.TemporaryDirectory() as folder:
            vault = Path(folder).resolve()
            with patch.object(snake, "VAULT", vault), patch.object(snake, "FIXTURE", vault / "SnakeBenchmark"):
                notes = snake.prepare()
                backend = CapturingMock()
                report = CanvasGateWorkflow(snake.FIXTURE / "workflow.canvas", vault).run(backend, max_calls=1)
                self.assertEqual(len(notes), 12)
                self.assertEqual(report["calls"], 1)
                self.assertEqual(report["outcome"], "completed")
                self.assertEqual(len(backend.inputs[0]), 3)
                sent = json.dumps(backend.inputs[0])
                for state in snake.STATES:
                    self.assertIn(state, sent)
                for requirement in ("createSnake(THREE)", "snake-head", "snake-body", "dispose", "deterministic absolute"):
                    self.assertIn(requirement, sent)
                self.assertNotIn("loaded a remote glTF", sent)
                self.assertNotIn("four small legs", sent)
                self.assertNotIn("marketing team", sent)


if __name__ == "__main__":
    unittest.main()
