import os
import tempfile
import unittest

from outage_messages import OUTAGE_MESSAGES, next_outage_message


class OutageMessageRotationTests(unittest.TestCase):
    def test_returns_each_message_in_order(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            index_file = os.path.join(temp_dir, "index.txt")

            messages = [
                next_outage_message(index_file)
                for _ in range(len(OUTAGE_MESSAGES))
            ]

        self.assertEqual(messages, list(OUTAGE_MESSAGES))

    def test_continues_from_saved_index_and_wraps(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            index_file = os.path.join(temp_dir, "index.txt")
            with open(index_file, "w", encoding="utf-8") as f:
                f.write(str(len(OUTAGE_MESSAGES) - 1))

            last_message = next_outage_message(index_file)
            first_message = next_outage_message(index_file)

        self.assertEqual(last_message, OUTAGE_MESSAGES[-1])
        self.assertEqual(first_message, OUTAGE_MESSAGES[0])

    def test_recovers_from_invalid_saved_index(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            index_file = os.path.join(temp_dir, "index.txt")
            with open(index_file, "w", encoding="utf-8") as f:
                f.write("invalid")

            message = next_outage_message(index_file)

        self.assertEqual(message, OUTAGE_MESSAGES[0])


if __name__ == "__main__":
    unittest.main()
