from twisted.words.protocols import irc
from twisted.internet import protocol

import re
import os
import dumbdbm

DBDIR  = 'db'
DBNAME = 'locks'

class LockBot(irc.IRCClient):
    def __init__(self):
        if not os.path.isdir(DBDIR):
            os.mkdir(DBDIR)
        dbpath = os.path.join(DBDIR, DBNAME)
        self.locks = dumbdbm.open(dbpath)
        self.password = 'testing'
    
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

        nick = user.strip().split('!')[0]
        print "privmsg: user %s, nick %s, channel %s, msg %s" % \
            (user, nick, channel, msg)

        # Ignore my own messages
        if nick == self.nickname:
            return

        # Snub private messages
        if channel == self.nickname:
            msg = "It isn't nice to whisper!  Play nice with the group."
            self.msg(nick, msg)
            return

        # Is client talking to me?
        targeted = msg.startswith(self.nickname + ':')
        if targeted:
            msg = msg[len(self.nickname + ':'):].lstrip()

        # First process global commands
        m = re.match("^lock\((.*)\)", msg)
        if m:
            resource = m.group(1).strip()
            print("Request from %s to lock \"%s\"" % (nick,resource))
            if resource in self.locks.keys():
                owner = self.locks[resource]
                self.msg(channel,
                         "%s: DENIED, %s is already locked by %s" %
                         (nick, resource, owner))
            else:
                self.locks[resource] = nick
                self.msg(channel,
                         "%s: GRANTED, %s's lock is all yours now" % 
                         (nick, resource))
   
        m = re.match("^unlock\((.*)\)", msg)
        if m:
            resource = m.group(1).strip()
            if resource not in self.locks.keys():
                self.msg(channel,
                         "%s: ERROR, %s is already free" % 
                         (nick, resource))
            else:
                del self.locks[resource]
                self.msg(channel,
                         "%s: RELEASED, %s lock is free" %
                         (nick, resource))

        # If the message is targeted, process the rest of the commands
        if not targeted:
            return

        m = re.match("^status.*", msg)
        if m:
            if len(self.locks) == 0:
                self.msg(channel, "%s: There are no locked resources" % nick )
            else:
                self.msg(channel, "%s: Status of locked resources:" % nick)
                for k,v in self.locks.items():
                    self.msg(channel, " resource:%s owner:%s" % (k,v))

class LockBotFactory(protocol.ClientFactory):
    protocol = LockBot

    def __init__(self, channel, nickname='lockbot'):
        self.channel = channel
        self.nickname = nickname

    def clientConnectionLost(self, connector, reason):
        print "Lost connection (%s), reconnecting." % (reason,)
        connector.connect()

    def clientConnectionFailed(self, connector, reason):
        print "Could not connect: %s" % (reason,)
