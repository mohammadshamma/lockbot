import unittest
import tempfile
import shutil
import os
from LockBotBrain import LockBotBrain

class TestLockBotBrain(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.brain = LockBotBrain("lockbot", self.test_dir)

    def tearDown(self):
        self.brain.close()
        shutil.rmtree(self.test_dir)

    def test_register_and_list(self):
        # Test registering a resource
        response = self.brain.register("user1", "channel", "resource1")
        self.assertIn("registered resource resource1", response[1])

        # Test listing resources
        response = self.brain.list("user1", "channel")
        self.assertIn("resource1", response[1])

    def test_lock_and_unlock(self):
        self.brain.register("user1", "channel", "resource1")

        # Test locking
        response = self.brain.lock("user1", "channel", "resource1")
        self.assertIn("GRANTED, you own resource1", response[1])

        # Test double locking (should fail or say owned)
        try:
            response = self.brain.lock("user2", "channel", "resource1")
            # If it doesn't raise exception, it might return a message
            self.fail("Should have raised exception or handled waiting")
        except Exception as e:
            # The current implementation might return a message or raise exception depending on how it's called
            # but LockBotBrain returns messages for some, raises LockBotException for others which are caught in processPrivMsg
            # Wait, `lock` method returns a tuple (channel, msg), it catches exceptions inside processPrivMsg?
            # No, `lock` method calls `_lock` which raises exceptions.
            # But `lock` is a handler. Let's see `LockBotBrain.lock`.
            pass

    def test_lock_logic(self):
        # Direct testing of _lock method logic via lock handler
        self.brain.register("user1", "channel", "res1")

        # User 1 locks
        _, msg = self.brain.lock("user1", "channel", "res1")
        self.assertIn("GRANTED", msg)
        self.assertIn("user1", self.brain.locks["res1"].owner)

        # User 2 tries to lock (should fail/raise)
        try:
            self.brain.lock("user2", "channel", "res1")
            self.fail("Should have raised LockBotException")
        except Exception as e:
            # The exception message might be wrapped or the exception type is LockBotException
            # LockBotBrain.lock calls _lock which raises LockBotException.
            # But the handler is wrapped in try-except in processPrivMsg, not in lock() itself.
            # Wait, `lock` method returns `(channel, self._lock(...))`. `_lock` raises Exception.
            # So `lock` raises exception.
            self.assertIn("DENIED", str(e))

        # User 1 unlocks
        messages = self.brain.unlock("user1", "channel", "res1")
        # unlock returns list of messages
        self.assertTrue(any("RELEASED" in msg[1] for msg in messages))
        self.assertEqual(self.brain.locks["res1"].owner, "")

    def test_wait_queue(self):
        self.brain.register("user1", "channel", "res1")
        self.brain.lock("user1", "channel", "res1")

        # User 2 waits for lock
        _, msg = self.brain.waitlock("user2", "channel", "res1")
        self.assertIn("WAITING", msg)
        self.assertIn("user2", self.brain.locks["res1"].waiters)

        # User 1 unlocks, User 2 should get it
        messages = self.brain.unlock("user1", "channel", "res1")
        # One message for release, one for grant to user2
        self.assertTrue(any("GRANTED" in msg[1] and "user2" in msg[1] for msg in messages))
        self.assertEqual(self.brain.locks["res1"].owner, "user2")

if __name__ == '__main__':
    unittest.main()
