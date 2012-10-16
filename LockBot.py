from twisted.words.protocols import irc
from twisted.internet import protocol

import re

class LockBot(irc.IRCClient):
    def __init__(self):
        self.locks = {}
    
    def _get_nickname(self):
        return self.factory.nickname
    nickname = property(_get_nickname)

    def signedOn(self):
        self.join(self.factory.channel)
        print "Signed on as %s." % (self.nickname,)

    def joined(self, channel):
        print "Joined %s." % (channel,)

    def privmsg(self, user, channel, msg):
        print "received: %s" % msg

        matchobj = re.match("^lock\((.*)\)", msg)
        if matchobj:
            resource = matchobj.group(1).strip()
            print "This is a lock message to lock \"%s\"" % resource 
            if resource in self.locks.keys():
                if self.locks[resource]:
                    print "Resource already locked (denied)"
                else:
                    print "Resource locked (granted)"
                    self.locks[resource] = True
            else:
                print "Creating resource (granted)"
                self.locks[resource] = True

        matchobj = re.match("^status.*", msg)
        if matchobj:
            print "The status is"
            for k,v in self.locks.items():
                print "resource:%s locked:%s" % (k,v)

        matchobj = re.match("^unlock\((.*)\)", msg)
        if matchobj:
            resource = matchobj.group(1).strip()
            if resource not in self.locks.keys():
                print "Unidentified resource (ERROR)"
            elif self.locks[resource]:
                print "Resource unlocked (released)"
                self.locks[resource] = False
            else:
                print "Resource already unlocked (ERROR)"

class LockBotFactory(protocol.ClientFactory):
    protocol = LockBot

    def __init__(self, channel, nickname='YourLock'):
        self.channel = channel
        self.nickname = nickname

    def clientConnectionLost(self, connector, reason):
        print "Lost connection (%s), reconnecting." % (reason,)
        connector.connect()

    def clientConnectionFailed(self, connector, reason):
        print "Could not connect: %s" % (reason,)
