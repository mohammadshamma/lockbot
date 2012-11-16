from twisted.words.protocols import irc
from twisted.internet import protocol

from LockBotBrain import LockBotBrain

class LockBot(irc.IRCClient):
    def __init__(self):
        self.brain = None

    def _get_nickname(self):
        return self.factory.nickname
    nickname = property(_get_nickname)

    def _get_password(self):
        return self.factory.password
    password = property(_get_password)

    def _get_dbdir(self):
        return self.factory.dbdir
    dbdir = property(_get_dbdir)

    def signedOn(self):
        print "Signed on as %s." % (self.nickname)
        self.brain = LockBotBrain(self.nickname)
        self.join(self.factory.channel)

    def joined(self, channel):
        print "Joined %s." % (channel)

    def privmsg(self, user, channel, msg):
        print "received: %s" % msg

        responses = self.brain.processPrivMsg(user, channel, msg)
        for channel, message in responses:
            self.msg(channel, message)

class LockBotFactory(protocol.ClientFactory):
    protocol = LockBot

    def __init__(self, channel, nickname, dbdir, password=None):
        self.channel = channel
        self.nickname = nickname
        self.password = password

    def clientConnectionLost(self, connector, reason):
        print "Lost connection (%s), reconnecting." % (reason,)
        connector.connect()

    def clientConnectionFailed(self, connector, reason):
        print "Could not connect: %s" % (reason,)
