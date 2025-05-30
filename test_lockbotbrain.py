import unittest
from LockBotBrain import LockBotBrain

import shutil
import tempfile

class TestLockBotBrain(unittest.TestCase):
    def setUp(self):
        self.test_db_dir = tempfile.mkdtemp()
        self.brain = LockBotBrain("testbot", self.test_db_dir)
        # Register a resource for testing
        response = self.brain.processPrivMsg("owner", "channel", "@testbot: register(res1)")
        self.assertEqual(len(response), 1, "Registration in setUp failed")
        self.assertEqual(response[0][0], "channel", "Registration in setUp failed")
        self.assertIn("registered resource res1", response[0][1], "Registration in setUp failed")

    def tearDown(self):
        # Explicitly close the db connection
        if hasattr(self.brain, 'locks') and hasattr(self.brain.locks, 'db'):
            db_instance = self.brain.locks.db
            if db_instance: # Check if it's not already None or other falsey value
                db_instance.close()
                self.brain.locks.db = None # Help prevent GC issues / double close
        
        # Attempt to remove the directory, ignore errors if it fails (e.g., due to timing on some systems)
        # but tests should have independent DBs anyway.
        shutil.rmtree(self.test_db_dir, ignore_errors=True)

    def test_create_lockbotbrain(self):
        self.assertIsNotNone(self.brain)

    def test_lock_available_resource(self):
        # Use trylock for immediate feedback, as 'lock' is 'waitlock'
        response = self.brain.processPrivMsg("user1", "channel", "@testbot: trylock(res1)")
        self.assertEqual(len(response), 1)
        self.assertEqual(response[0][0], "channel")
        self.assertIn("GRANTED, you own res1", response[0][1])
        self.assertEqual(self.brain.locks['res1'].owner, "user1")

    def test_lock_already_locked_resource(self):
        self.brain.processPrivMsg("user1", "channel", "@testbot: trylock(res1)") # user1 locks res1
        response = self.brain.processPrivMsg("user2", "channel", "@testbot: trylock(res1)") # user2 tries to lock res1
        self.assertEqual(len(response), 1)
        self.assertEqual(response[0][0], "channel")
        self.assertIn("DENIED, res1 is already locked by user1", response[0][1])
        self.assertEqual(self.brain.locks['res1'].owner, "user1") # Still user1

    def test_unlock_owned_resource(self):
        self.brain.processPrivMsg("user1", "channel", "@testbot: trylock(res1)") # user1 locks res1
        response = self.brain.processPrivMsg("user1", "channel", "@testbot: unlock(res1)")
        self.assertEqual(len(response), 1)
        self.assertEqual(response[0][0], "channel")
        self.assertIn("RELEASED, resource res1 is free", response[0][1])
        self.assertEqual(self.brain.locks['res1'].owner, "")

    def test_unlock_resource_locked_by_another(self):
        self.brain.processPrivMsg("user1", "channel", "@testbot: trylock(res1)") # user1 locks res1
        response = self.brain.processPrivMsg("user2", "channel", "@testbot: unlock(res1)") # user2 tries to unlock
        self.assertEqual(len(response), 1)
        self.assertEqual(response[0][0], "channel")
        self.assertIn("DENIED, user1 holds the lock on res1", response[0][1])
        self.assertEqual(self.brain.locks['res1'].owner, "user1") # Still user1

    def test_unlock_free_resource(self):
        # Resource is registered but not locked
        response = self.brain.processPrivMsg("user1", "channel", "@testbot: unlock(res1)")
        self.assertEqual(len(response), 1)
        self.assertEqual(response[0][0], "channel")
        self.assertIn("res1 is already free", response[0][1])
        self.assertEqual(self.brain.locks['res1'].owner, "")

    # --- Registration Tests ---
    def test_register_new_resource(self):
        # res1 is registered in setUp, let's use res2
        response = self.brain.processPrivMsg("user1", "channel", "@testbot: register(res2)")
        self.assertEqual(len(response), 1)
        self.assertEqual(response[0][0], "channel")
        self.assertIn("user1: registered resource res2", response[0][1])
        self.assertIn("res2", self.brain.locks.keys())

    def test_register_existing_resource(self):
        # res1 is already registered in setUp
        response = self.brain.processPrivMsg("user1", "channel", "@testbot: register(res1)")
        self.assertEqual(len(response), 1)
        self.assertEqual(response[0][0], "channel")
        self.assertIn('ERROR, resource "res1" is already registered', response[0][1])

    # --- Unregistration Tests ---
    def test_unregister_existing_resource(self):
        # res1 is registered in setUp
        response = self.brain.processPrivMsg("user1", "channel", "@testbot: unregister(res1)")
        self.assertEqual(len(response), 1)
        self.assertEqual(response[0][0], "channel")
        self.assertIn("user1: removed resource res1", response[0][1])
        self.assertNotIn("res1", self.brain.locks.keys())

    def test_unregister_non_existing_resource(self):
        response = self.brain.processPrivMsg("user1", "channel", "@testbot: unregister(resNonExistent)")
        self.assertEqual(len(response), 1)
        self.assertEqual(response[0][0], "channel")
        self.assertIn('ERROR: unrecognized resource "resNonExistent"', response[0][1])

    def test_unregister_locked_resource(self):
        # res1 is registered in setUp
        # Lock res1
        self.brain.processPrivMsg("userLocker", "channel", "@testbot: trylock(res1)")
        
        # Attempt to unregister res1 by another user
        response = self.brain.processPrivMsg("user1", "channel", "@testbot: unregister(res1)")
        self.assertEqual(len(response), 1)
        self.assertEqual(response[0][0], "channel")
        # The error message includes the lock details, which can be complex.
        # Checking for the core part of the error.
        self.assertIn('ERROR, resource "res1" is locked by', response[0][1]) 
        self.assertIn("userLocker", response[0][1]) # Check if locker is mentioned
        self.assertIn("res1", self.brain.locks.keys()) # Resource should still be registered

    # --- Waiting List Tests ---
    def test_user_added_to_waiting_list(self):
        # user1 locks res1
        self.brain.processPrivMsg("user1", "channel", "@testbot: trylock(res1)")
        self.assertEqual(self.brain.locks["res1"].owner, "user1")

        # user2 tries to lock res1 using 'lock' (which is waitlock)
        response = self.brain.processPrivMsg("user2", "channel", "@testbot: lock(res1)")
        self.assertEqual(len(response), 1)
        self.assertEqual(response[0][0], "channel")
        # Updated assertion to match the actual detailed message
        self.assertIn("user2: WAITING for res1 (owner: user1 waiters: user2)", response[0][1])
        self.assertEqual(self.brain.locks["res1"].owner, "user1") # Still user1
        self.assertEqual(self.brain.locks["res1"].waiters, ["user2"])

    def test_next_user_gets_lock_on_unlock(self):
        # user1 locks res1
        self.brain.processPrivMsg("user1", "channel", "@testbot: trylock(res1)")
        # user2 waits for res1
        self.brain.processPrivMsg("user2", "channel", "@testbot: lock(res1)")
        # user3 waits for res1
        self.brain.processPrivMsg("user3", "channel", "@testbot: lock(res1)")
        self.assertEqual(self.brain.locks["res1"].waiters, ["user2", "user3"])

        # user1 unlocks res1
        response = self.brain.processPrivMsg("user1", "channel", "@testbot: unlock(res1)")
        # Expected: user1 releases, user2 gets lock.
        # The response list can have multiple messages.
        # 1. user1: RELEASED...
        # 2. user2: GRANTED... (from _lock call inside unlock)
        self.assertTrue(len(response) >= 2, "Expected at least two messages in response")
        
        found_user1_released = False
        found_user2_granted = False
        for _, msg_text in response:
            if "user1: RELEASED" in msg_text and "res1" in msg_text:
                found_user1_released = True
            if "user2: GRANTED, you own res1" in msg_text: # LockBotBrain._lock uses "you own" when caller==assignee
                found_user2_granted = True
        
        self.assertTrue(found_user1_released, "user1 release message not found")
        self.assertTrue(found_user2_granted, "user2 grant message not found")

        self.assertEqual(self.brain.locks["res1"].owner, "user2")
        self.assertEqual(self.brain.locks["res1"].waiters, ["user3"])

    def test_user_gives_up_waiting_spot_on_unlock(self):
        # user1 locks res1
        self.brain.processPrivMsg("user1", "channel", "@testbot: trylock(res1)")
        # user2 waits for res1
        self.brain.processPrivMsg("user2", "channel", "@testbot: lock(res1)")
        # user3 waits for res1
        self.brain.processPrivMsg("user3", "channel", "@testbot: lock(res1)")
        self.assertEqual(self.brain.locks["res1"].owner, "user1")
        self.assertEqual(self.brain.locks["res1"].waiters, ["user2", "user3"])

        # user2 (a waiter) issues an unlock command for res1
        response = self.brain.processPrivMsg("user2", "channel", "@testbot: unlock(res1)")
        self.assertEqual(len(response), 1)
        self.assertEqual(response[0][0], "channel")
        self.assertIn("user2: GAVE UP, no longer waiting for resource res1", response[0][1])
        self.assertEqual(self.brain.locks["res1"].owner, "user1") # Still user1
        self.assertEqual(self.brain.locks["res1"].waiters, ["user3"]) # user2 removed

    def test_waiting_list_fifo_order(self):
        # This is implicitly tested by test_next_user_gets_lock_on_unlock
        # user1 locks, user2 waits, user3 waits. Unlock -> user2 gets it.
        # We can add another layer if needed.
        self.test_next_user_gets_lock_on_unlock() # Relies on the previous test's logic

    def test_multiple_users_waiting_lock_release(self):
        # This is also covered by test_next_user_gets_lock_on_unlock
        # user1 (owner), user2 (waiter1), user3 (waiter2)
        # user1 unlocks -> user2 becomes owner, user3 remains waiter.
        self.test_next_user_gets_lock_on_unlock()

    def test_trylock_does_not_add_to_waiting_list(self):
        # user1 locks res1
        self.brain.processPrivMsg("user1", "channel", "@testbot: trylock(res1)")
        self.assertEqual(self.brain.locks["res1"].owner, "user1")

        # user2 tries to trylock res1 (using 'trylock' command)
        response = self.brain.processPrivMsg("user2", "channel", "@testbot: trylock(res1)")
        self.assertEqual(len(response), 1)
        self.assertEqual(response[0][0], "channel")
        self.assertIn("DENIED, res1 is already locked by user1", response[0][1])
        self.assertEqual(self.brain.locks["res1"].owner, "user1") # Still user1
        self.assertEqual(self.brain.locks["res1"].waiters, []) # Waitlist is empty

    # --- Assignlock Tests ---
    def test_assignlock_successful(self):
        # res1 is registered in setUp
        response = self.brain.processPrivMsg("admin", "channel", "@testbot: assignlock(res1, userassignee)")
        self.assertEqual(len(response), 1)
        self.assertEqual(response[0][0], "channel")
        self.assertIn("admin: GRANTED, userassignee owns res1", response[0][1])
        self.assertEqual(self.brain.locks["res1"].owner, "userassignee")

    def test_assignlock_unregistered_resource(self):
        response = self.brain.processPrivMsg("admin", "channel", "@testbot: assignlock(resNonExistent, userassignee)")
        self.assertEqual(len(response), 1)
        self.assertEqual(response[0][0], "channel")
        self.assertIn('ERROR: unrecognized resource "resNonExistent"', response[0][1])

    def test_assignlock_to_current_assignee(self):
        # userassignee already owns res1
        self.brain.processPrivMsg("admin", "channel", "@testbot: assignlock(res1, userassignee)")
        # Now admin tries to assign it to userassignee again
        response = self.brain.processPrivMsg("admin", "channel", "@testbot: assignlock(res1, userassignee)")
        self.assertEqual(len(response), 1)
        self.assertEqual(response[0][0], "channel")
        self.assertIn("userassignee already hold the lock for resource res1", response[0][1])
        self.assertEqual(self.brain.locks["res1"].owner, "userassignee")

    def test_assignlock_to_self_when_assignee_owns(self):
        # userassignee owns res1
        self.brain.processPrivMsg("admin", "channel", "@testbot: assignlock(res1, userassignee)") 
        # admin (caller) tries to assign to admin (new assignee) when userassignee currently owns it
        response = self.brain.processPrivMsg("admin", "channel", "@testbot: assignlock(res1, admin)")
        self.assertEqual(len(response), 1)
        self.assertEqual(response[0][0], "channel")
        self.assertIn("DENIED, res1 is already locked by userassignee", response[0][1])
        self.assertEqual(self.brain.locks["res1"].owner, "userassignee")

    def test_assignlock_resource_locked_by_third_user(self):
        # user1 locks res1
        self.brain.processPrivMsg("user1", "channel", "@testbot: trylock(res1)")
        # admin tries to assign res1 (locked by user1) to userassignee
        response = self.brain.processPrivMsg("admin", "channel", "@testbot: assignlock(res1, userassignee)")
        self.assertEqual(len(response), 1)
        self.assertEqual(response[0][0], "channel")
        self.assertIn("DENIED, res1 is already locked by user1", response[0][1])
        self.assertEqual(self.brain.locks["res1"].owner, "user1")

    # --- Freelock Tests ---
    def test_freelock_successful(self):
        # user1 locks res1
        self.brain.processPrivMsg("user1", "channel", "@testbot: trylock(res1)")
        self.assertEqual(self.brain.locks["res1"].owner, "user1")

        # admin frees res1
        response = self.brain.processPrivMsg("admin", "channel", "@testbot: freelock(res1)")
        # Expected messages:
        # 1. admin: RELEASED, resource res1 is free
        # 2. user1: your lock on res1 has been released by admin
        self.assertEqual(len(response), 2)
        
        admin_freed_found = any("admin: RELEASED, resource res1 is free" in msg[1] for msg in response if msg[0] == "channel")
        owner_notified_found = any("user1: your lock on res1 has been released by admin" in msg[1] for msg in response if msg[0] == "channel")

        self.assertTrue(admin_freed_found, "Admin release message not found")
        self.assertTrue(owner_notified_found, "Owner notification message not found")
        self.assertEqual(self.brain.locks["res1"].owner, "") # Resource is now free

    def test_freelock_unregistered_resource(self):
        response = self.brain.processPrivMsg("admin", "channel", "@testbot: freelock(resNonExistent)")
        self.assertEqual(len(response), 1)
        self.assertEqual(response[0][0], "channel")
        self.assertIn('ERROR: unrecognized resource "resNonExistent"', response[0][1])

    def test_freelock_already_free_resource(self):
        # res1 is registered but not locked
        response = self.brain.processPrivMsg("admin", "channel", "@testbot: freelock(res1)")
        self.assertEqual(len(response), 1)
        self.assertEqual(response[0][0], "channel")
        self.assertIn("ERROR: resource res1 is already unlocked", response[0][1])

    def test_freelock_with_waiting_list(self):
        # user1 locks res1
        self.brain.processPrivMsg("user1", "channel", "@testbot: trylock(res1)")
        # user2 waits for res1
        self.brain.processPrivMsg("user2", "channel", "@testbot: lock(res1)")
        # user3 waits for res1
        self.brain.processPrivMsg("user3", "channel", "@testbot: lock(res1)")
        self.assertEqual(self.brain.locks["res1"].owner, "user1")
        self.assertEqual(self.brain.locks["res1"].waiters, ["user2", "user3"])

        # admin frees res1
        response = self.brain.processPrivMsg("admin", "channel", "@testbot: freelock(res1)")
        # Expected messages:
        # 1. admin: RELEASED, resource res1 is free
        # 2. user1: your lock on res1 has been released by admin
        # 3. user2: GRANTED, you own res1 (as user2 was next in line)
        self.assertTrue(len(response) >= 3, "Expected at least three messages in response")

        admin_freed_found = any("admin: RELEASED, resource res1 is free" in msg[1] for msg in response if msg[0] == "channel")
        owner_notified_found = any("user1: your lock on res1 has been released by admin" in msg[1] for msg in response if msg[0] == "channel")
        # Corrected expected message: admin (caller of freelock) grants to user2 (promoted waiter)
        user2_granted_found = any("admin: GRANTED, user2 owns res1" in msg[1] for msg in response if msg[0] == "channel")
        
        self.assertTrue(admin_freed_found, "Admin release message not found for freelock with waitlist")
        self.assertTrue(owner_notified_found, "Owner notification message not found for freelock with waitlist")
        self.assertTrue(user2_granted_found, "Next waiter grant message not found for freelock with waitlist")

        self.assertEqual(self.brain.locks["res1"].owner, "user2") # user2 should now own the lock
        self.assertEqual(self.brain.locks["res1"].waiters, ["user3"]) # user3 should still be waiting

    # --- Status and List Commands Tests ---

    # Status / Listlocked
    def test_status_no_locked_resources(self):
        # res1 is registered in setUp but not locked initially by these tests
        response = self.brain.processPrivMsg("user1", "channel", "@testbot: status")
        self.assertEqual(len(response), 1)
        self.assertEqual(response[0], ("channel", "There are no locked resources"))

    def test_status_listlocked_alias(self):
        response_status = self.brain.processPrivMsg("user1", "channel", "@testbot: status")
        response_listlocked = self.brain.processPrivMsg("user1", "channel", "@testbot: listlocked")
        self.assertEqual(response_status, response_listlocked)

    def test_status_single_lock_no_waiters(self):
        self.brain.processPrivMsg("owner1", "channel", "@testbot: trylock(res1)")
        response = self.brain.processPrivMsg("user1", "channel", "@testbot: status")
        expected_messages = [
            ("channel", "Status of locked resources:"),
            ("channel", "  resource: res1 owner: owner1")
        ]
        self.assertEqual(response, expected_messages)

    def test_status_single_lock_with_waiters(self):
        self.brain.processPrivMsg("owner1", "channel", "@testbot: trylock(res1)")
        self.brain.processPrivMsg("waiter1", "channel", "@testbot: lock(res1)")
        self.brain.processPrivMsg("waiter2", "channel", "@testbot: lock(res1)")
        response = self.brain.processPrivMsg("user1", "channel", "@testbot: status")
        expected_messages = [
            ("channel", "Status of locked resources:"),
            ("channel", "  resource: res1 owner: owner1 waiters: waiter1,waiter2")
        ]
        self.assertEqual(response, expected_messages)

    def test_status_multiple_locks_mixed_waiters(self):
        # Register another resource
        self.brain.processPrivMsg("admin", "channel", "@testbot: register(res2)")
        
        self.brain.processPrivMsg("owner1", "channel", "@testbot: trylock(res1)")
        self.brain.processPrivMsg("waiter1_res1", "channel", "@testbot: lock(res1)")
        
        self.brain.processPrivMsg("owner2", "channel", "@testbot: trylock(res2)")
        self.brain.processPrivMsg("waiter1_res2", "channel", "@testbot: lock(res2)")
        self.brain.processPrivMsg("waiter2_res2", "channel", "@testbot: lock(res2)")

        response = self.brain.processPrivMsg("user1", "channel", "@testbot: status")
        # Order of resources in status is sorted by resource name
        expected_messages = [
            ("channel", "Status of locked resources:"),
            ("channel", "  resource: res1 owner: owner1 waiters: waiter1_res1"),
            ("channel", "  resource: res2 owner: owner2 waiters: waiter1_res2,waiter2_res2")
        ]
        self.assertEqual(response, expected_messages)

    # Listfree
    def test_listfree_no_resources_free(self):
        # res1 is registered, lock it
        self.brain.processPrivMsg("owner1", "channel", "@testbot: trylock(res1)")
        response = self.brain.processPrivMsg("user1", "channel", "@testbot: listfree")
        self.assertEqual(len(response), 1)
        self.assertEqual(response[0], ("channel", "There are no unlocked resources"))
        
    def test_listfree_all_resources_free(self):
        # res1 is registered in setUp and is free
        self.brain.processPrivMsg("admin", "channel", "@testbot: register(res2)")
        self.brain.processPrivMsg("admin", "channel", "@testbot: register(res3)")
        response = self.brain.processPrivMsg("user1", "channel", "@testbot: listfree")
        self.assertEqual(len(response), 1)
        # Order is sorted
        self.assertEqual(response[0], ("channel", "Unlocked resources: res1, res2, res3"))

    def test_listfree_mixed_locked_and_free(self):
        self.brain.processPrivMsg("admin", "channel", "@testbot: register(res2)")
        self.brain.processPrivMsg("admin", "channel", "@testbot: register(res3)")
        
        self.brain.processPrivMsg("owner1", "channel", "@testbot: trylock(res1)") # Lock res1
        # res2, res3 are free
        
        response = self.brain.processPrivMsg("user1", "channel", "@testbot: listfree")
        self.assertEqual(len(response), 1)
        self.assertEqual(response[0], ("channel", "Unlocked resources: res2, res3"))

    # List
    def test_list_no_registered_resources(self):
        # Unregister res1 from setUp
        self.brain.processPrivMsg("admin", "channel", "@testbot: unregister(res1)")
        response = self.brain.processPrivMsg("user1", "channel", "@testbot: list")
        self.assertEqual(len(response), 1)
        self.assertEqual(response[0], ("channel", "There are no registered resources"))

    def test_list_all_registered_resources(self):
        # res1 is from setUp
        self.brain.processPrivMsg("admin", "channel", "@testbot: register(res2)")
        self.brain.processPrivMsg("admin", "channel", "@testbot: register(res0)") # For sort order check
        
        self.brain.processPrivMsg("owner1", "channel", "@testbot: trylock(res1)") # Lock one
        
        response = self.brain.processPrivMsg("user1", "channel", "@testbot: list")
        self.assertEqual(len(response), 1)
        # Order is sorted
        self.assertEqual(response[0], ("channel", "List of registered resources: res0, res1, res2"))

    # --- Error Handling Tests ---
    def test_unrecognized_command(self):
        response = self.brain.processPrivMsg("user1", "channel", "@testbot: foobarcommand(res1)")
        self.assertEqual(len(response), 1)
        self.assertEqual(response[0][0], "channel")
        self.assertIn("user1: Unrecognized command, try '@testbot: help'", response[0][1])

    def test_command_missing_resource_name_lock(self):
        # Test lock()
        response = self.brain.processPrivMsg("user1", "channel", "@testbot: trylock()")
        self.assertEqual(len(response), 1) 
        # (.*) in regex matches empty string from "()", strip() keeps it empty.
        # splitResources("") then raises the error.
        self.assertIn("ERROR: empty resource names are not allowed", response[0][1])

        # Test lock( ) - This will be "ERROR: empty resource names are not allowed"
        response = self.brain.processPrivMsg("user1", "channel", "@testbot: trylock( )")
        self.assertEqual(len(response), 1) 
        self.assertIn("ERROR: empty resource names are not allowed", response[0][1])

    def test_command_empty_resource_name_in_list(self):
        # res1 is registered
        # This now returns 2 messages because resourcestr "res1,,res2" contains a comma
        response = self.brain.processPrivMsg("user1", "channel", "@testbot: trylock(res1,,res2)")
        self.assertEqual(len(response), 2, "Expected 2 messages for empty resource name in list")
        self.assertEqual(response[0][0], "channel")
        self.assertIn("user1: ERROR: empty resource names are not allowed", response[0][1])
        self.assertIn("user1: no resources locked", response[1][1]) # Verb is 'locked'


    def test_command_duplicate_resource_name_in_list(self):
        # res1 is registered
        response = self.brain.processPrivMsg("user1", "channel", "@testbot: trylock(res1,res1)")
        # This returns 2 messages because resourcestr "res1,res1" contains a comma
        self.assertEqual(len(response), 2, "Expected 2 messages for duplicate resource name in list")
        self.assertEqual(response[0][0], "channel")
        self.assertIn("user1: ERROR: duplicate resource name", response[0][1])
        self.assertIn("user1: no resources locked", response[1][1]) # Verb is 'locked'


    def test_unlock_non_existent_resource_strict(self):
        # Ensuring no Levenshtein match for a clearly different name
        self.brain.processPrivMsg("admin", "channel", "@testbot: register(resourcealpha)")
        response = self.brain.processPrivMsg("user1", "channel", "@testbot: unlock(completelydifferent)")
        self.assertEqual(len(response), 1)
        self.assertEqual(response[0][0], "channel")
        self.assertIn('ERROR: unrecognized resource "completelydifferent"', response[0][1])

    # Levenshtein distance tests
    def test_levenshtein_corrects_minor_misspelling(self):
        # res1 is registered in setUp.
        # trylock res1 with a misspelling
        response = self.brain.processPrivMsg("user1", "channel", "@testbot: trylock(resl)") # "resl" -> "res1"
        self.assertEqual(len(response), 1)
        self.assertEqual(response[0][0], "channel")
        self.assertIn("user1: GRANTED, you own res1", response[0][1])
        self.assertEqual(self.brain.locks["res1"].owner, "user1")

    def test_levenshtein_ambiguous_misspelling(self):
        self.brain.processPrivMsg("admin", "channel", "@testbot: register(rest)") # close to res1
        # "resl" is close to "res1" and "rest"
        # Current Levenshtein logic might pick one if scores are equal, or deny if multiple have same best score.
        # The getlock code: `if best[0] < 0.5 or len([c for c in ratios if c[0] == best[0]]) > 1: return name`
        # So, if multiple have the same best ratio, it returns the original misspelled name.
        response = self.brain.processPrivMsg("user1", "channel", "@testbot: trylock(resl)")
        self.assertEqual(len(response), 1)
        self.assertEqual(response[0][0], "channel")
        # It should fail as "resl" is not registered, and it's ambiguous.
        self.assertIn('ERROR: unrecognized resource "resl"', response[0][1])

    def test_levenshtein_too_different_misspelling(self):
        # res1 is registered.
        response = self.brain.processPrivMsg("user1", "channel", "@testbot: trylock(completelydifferent)")
        self.assertEqual(len(response), 1)
        self.assertEqual(response[0][0], "channel")
        self.assertIn('ERROR: unrecognized resource "completelydifferent"', response[0][1])

    def test_assignlock_empty_assignee(self):
        response = self.brain.processPrivMsg("admin", "channel", "@testbot: assignlock(res1, )")
        self.assertEqual(len(response), 1)
        self.assertEqual(response[0][0], "channel")
        # This should be caught by the strip() in processPrivMsg leading to an empty assignee.
        # _lock will then try to use an empty string as assignee.
        # Depending on how _lock handles empty assignee string, this might be a specific error or unexpected behavior.
        # Let's assume an empty assignee is not allowed by _lock or results in a specific message.
        # If assignee becomes "", then self.locks[r].owner = "" -> effectively freeing it.
        # The message would be "admin: GRANTED,  owns res1"
        # This is probably not desired. An empty assignee should ideally be an error.
        # Current _lock doesn't explicitly block empty assignee.
        # Now expects an error because empty assignee is disallowed in _lock
        self.assertIn("ERROR: assignee cannot be empty", response[0][1])
        # Check that res1 owner remains empty (its initial state)
        self.assertEqual(self.brain.locks["res1"].owner, "", "Owner should be unchanged on error")

    def test_assignlock_resource_and_assignee_missing(self):
        response = self.brain.processPrivMsg("admin", "channel", "@testbot: assignlock()")
        self.assertEqual(len(response), 1)
        self.assertIn("Unrecognized command", response[0][1])

        response = self.brain.processPrivMsg("admin", "channel", "@testbot: assignlock( , )")
        self.assertEqual(len(response), 1)
        # This will fail first on "assignee cannot be empty" due to order of checks in _lock
        self.assertIn("ERROR: assignee cannot be empty", response[0][1])

    # --- Help Command Test ---
    def test_help_command(self):
        response = self.brain.processPrivMsg("user1", "channel", "@testbot: help")

        # First message is the header
        self.assertEqual(response[0], ("channel", "List of lockbot commands:"))

        # Define expected commands, their arguments, and descriptions
        # This needs to match the order and formatting from LockBotBrain.help()
        # The padding calculation in LockBotBrain.help() makes exact string matching crucial.
        # Let's get the actual padding by inspecting one of the lines or by pre-calculating.
        # The format is " <cmdpart>:<padding_spaces><description>"
        
        # Based on current commands and their argspec in LockBotBrain:
        # lock <resourcestr> (maps to _lock via self.lock)
        # unlock <resourcestr>
        # assignlock <assignee> <resourcestr> (Note: getCmdArguments gets names from handler, which is assignlock(self, nick, channel, resourcestr, assignee))
        # freelock <resourcestr>
        # waitlock <resourcestr> (maps to _lock via self.waitlock)
        # register <resourcestr>
        # unregister <resourcestr>
        # status <>
        # listlocked <> (alias for status, might not appear if processedHandlers filters it)
        # listfree <>
        # list <>
        # help <>
        # trylock maps to self.lock, so it's covered by 'lock'.
        # defaulthandler is not a user command.

        # Expected structure: (command_and_args, description)
        # The help method processes handlers. If multiple rules map to the same handler, it's listed once.
        # `self.lock` (for trylock) and `self.waitlock` (for lock) are distinct handlers.
        # `self.status` (for status, listlocked) - listlocked might be skipped by processedHandlers.

        expected_help_items = [
            ("lock <resourcestr>", "take hold of a lock on a resource"), # from self.lock (used by trylock)
            ("unlock <resourcestr>", "release the resource lock"),
            ("assignlock <resourcestr> <assignee>", "assign a resource lock to someone else other than the caller"),
            ("freelock <resourcestr>", "release a resource lock even if the caller does not hold the lock (USE WITH CAUTION)"),
            ("waitlock <resourcestr>", "try to take the lock, or get on queue if it is currently locked"), # from self.waitlock
            ("register <resourcestr>", "add a new resource to the database"),
            ("unregister <resourcestr>", "remove a resource from the database"),
            ("status", "list locked resources and their owners"), # self.status handler
            ("listfree", "list unlocked resources"),
            ("list", "list all registered resources"),
            ("help", "display this help message")
        ]
        
        # Determine padding: find the longest cmdpart
        cmd_parts = [item[0] for item in expected_help_items]
        padding_len = max([len(cp) for cp in cmd_parts])

        expected_messages = [("channel", "List of lockbot commands:")]
        for cmdpart_orig, description in expected_help_items:
            cmdpart = cmdpart_orig.strip() # Ensure no leading/trailing spaces from definition
            spaces = (padding_len - len(cmdpart) + 1) * ' '
            expected_messages.append(("channel", f" {cmdpart}:{spaces}{description}"))
            
        self.assertEqual(len(response), len(expected_messages), "Number of help lines mismatch")
        for i in range(len(response)):
            self.assertEqual(response[i][0], expected_messages[i][0], f"Channel mismatch for line {i+1}")
            self.assertEqual(response[i][1], expected_messages[i][1], f"Message mismatch for line {i+1}")

if __name__ == '__main__':
    unittest.main()
