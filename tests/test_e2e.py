from twisted.trial import unittest
from twisted.internet import reactor, protocol, defer, error
from twisted.words.protocols import irc
import sys
import os
import shutil
import time

# Define the Mock IRC Server Protocol and Factory locally for in-process execution
class MockIRC(irc.IRC):
    def connectionMade(self):
        if self.factory:
            self.factory.clients.append(self)

    def connectionLost(self, reason):
        if self.factory and self in self.factory.clients:
            self.factory.clients.remove(self)

    def irc_NICK(self, prefix, params):
        self.nickname = params[0]
        self.sendMessage("001", params[0], "Welcome to MockIRC")

    def irc_USER(self, prefix, params):
        self.username = params[0]
        self.realname = params[3]

    def irc_JOIN(self, prefix, params):
        channel = params[0]
        # Echo join to all clients (simplified)
        for client in self.factory.clients:
             client.sendMessage("JOIN", channel, prefix=f"{self.nickname}!{self.username}@host")

    def irc_PRIVMSG(self, prefix, params):
        target = params[0]
        msg = params[1]
        sender = f"{self.nickname}!{self.username}@host"

        if target.startswith('#'):
            for client in self.factory.clients:
                if client != self:
                    # Manually send line to ensure colon is present for trailing parameter
                    client.sendLine(f":{sender} PRIVMSG {target} :{msg}")
        else:
            # Maybe private message?
             for client in self.factory.clients:
                if getattr(client, 'nickname', '') == target:
                     client.sendLine(f":{sender} PRIVMSG {target} :{msg}")

    def irc_PING(self, prefix, params):
        if params:
            self.sendMessage("PONG", params[-1])
        else:
            self.sendMessage("PONG")

    def irc_PASS(self, prefix, params):
        pass

    def irc_QUIT(self, prefix, params):
        self.transport.loseConnection()

class MockIRCFactory(protocol.Factory):
    def __init__(self):
        self.clients = []

    def buildProtocol(self, addr):
        p = MockIRC()
        p.factory = self
        return p

# Test Client
class TestClient(irc.IRCClient):
    nickname = "testuser"

    def __init__(self):
        self.on_welcome = defer.Deferred()
        self.received_messages = []
        self.message_waiters = []

    def connectionMade(self):
        irc.IRCClient.connectionMade(self)

    def signedOn(self):
        if not self.on_welcome.called:
            self.on_welcome.callback(self)

    def privmsg(self, user, channel, msg):
        self.received_messages.append(msg)
        # Check if any waiters are waiting for this message
        to_remove = []
        for d, predicate in self.message_waiters:
            if predicate(msg):
                d.callback(msg)
                to_remove.append((d, predicate))

        for item in to_remove:
            self.message_waiters.remove(item)

    def waitForMessage(self, predicate):
        # Check if already received
        for msg in self.received_messages:
            if predicate(msg):
                return defer.succeed(msg)

        d = defer.Deferred()
        self.message_waiters.append((d, predicate))
        return d

class TestClientFactory(protocol.ClientFactory):
    def __init__(self):
        self.client = TestClient()

    def buildProtocol(self, addr):
        return self.client

    def clientConnectionFailed(self, connector, reason):
        if not self.client.on_welcome.called:
            self.client.on_welcome.errback(reason)

class LockBotE2ETest(unittest.TestCase):
    SERVER_PORT = 16667
    CONFIG_FILE = "e2e_lockbot.conf"
    DB_DIR = "e2e_db"

    def setUp(self):
        # Determine repo root
        cwd = os.getcwd()
        if os.path.basename(cwd) == "_trial_temp":
             repo_root = os.path.dirname(cwd)
        else:
             repo_root = cwd

        # Start Mock Server
        self.server_factory = MockIRCFactory()
        self.server_port = reactor.listenTCP(self.SERVER_PORT, self.server_factory)

        # Prepare Config
        # Ensure directory exists
        self.config_path = os.path.join(repo_root, "tests", self.CONFIG_FILE)
        self.db_dir = os.path.join(repo_root, "tests", self.DB_DIR)

        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)

        with open(self.config_path, "w") as f:
            f.write(f"""[lockbot]
server   = localhost
port     = {self.SERVER_PORT}
password =
channel  = testchannel
nickname = lockbot
dbdir    = {self.db_dir}
usessl   = no
""")

        # Start LockBot as subprocess
        main_py = os.path.join(repo_root, "Main.py")

        class SimpleProcessProtocol(protocol.ProcessProtocol):
            def __init__(self):
                self.done = defer.Deferred()
            def outReceived(self, data):
                pass
            def errReceived(self, data):
                pass
            def processEnded(self, reason):
                self.done.callback(None)

        self.bot_protocol = SimpleProcessProtocol()
        self.bot_process = reactor.spawnProcess(
            self.bot_protocol, sys.executable, [sys.executable, main_py, self.config_path],
            env=os.environ,
            path=repo_root
        )

        # Connect Test Client
        self.client_factory = TestClientFactory()
        reactor.connectTCP("localhost", self.SERVER_PORT, self.client_factory)

        return self.client_factory.client.on_welcome

    @defer.inlineCallbacks
    def tearDown(self):
        # Disconnect test client
        if self.client_factory.client.transport:
            self.client_factory.client.quit()

        # Kill bot process
        try:
            self.bot_process.signalProcess('TERM')
        except error.ProcessExitedAlready:
            pass

        yield self.bot_protocol.done

        # Stop listening
        yield self.server_port.stopListening()
        self._cleanup_files()

    def _cleanup_files(self):
        if hasattr(self, 'config_path') and os.path.exists(self.config_path):
            os.remove(self.config_path)
        if hasattr(self, 'db_dir') and os.path.exists(self.db_dir):
            shutil.rmtree(self.db_dir)

    @defer.inlineCallbacks
    def test_full_flow(self):
        client = self.client_factory.client

        # Join channel
        client.join("#testchannel")

        # Wait a bit for bot to join (simple way, or we could add logic to MockIRC to notify us)
        d = defer.Deferred()
        reactor.callLater(2, d.callback, None)
        yield d

        # 1. Register resource
        client.msg("#testchannel", "lockbot: register res1")
        yield client.waitForMessage(lambda m: "registered resource res1" in m)

        # 2. Lock resource
        client.msg("#testchannel", "lockbot: lock res1")
        yield client.waitForMessage(lambda m: "GRANTED, you own res1" in m)

        # 3. Verify it is locked (try to lock with another user? mocked here as same connection but let's assume valid check)
        # We can just check status
        client.msg("#testchannel", "lockbot: status")
        yield client.waitForMessage(lambda m: "res1 owner: testuser" in m)

        # 4. Unlock
        client.msg("#testchannel", "lockbot: unlock res1")
        yield client.waitForMessage(lambda m: "RELEASED" in m)
