import re
import os
import dumbdbm

DBDIR  = 'db'
DBNAME = 'locks'

class LockBotBrain(object):

    def __init__(self, nickname):

        if not os.path.isdir(DBDIR):
            os.mkdir(DBDIR)
        dbpath = os.path.join(DBDIR, DBNAME)

        self.locks = dumbdbm.open(dbpath)
        self.nickname = nickname
        self.rules = self.interpolateRules(nickname)

    def interpolateRules(self, nickname):
        rules = self.getRules()
        irules = []
        for rule in rules:
            irule = (rule[0].replace('@BOTNAME@', nickname),
                     rule[1])
            irules.append(irule)
        return irules

    def processPrivMsg(self, user, channel, msg):

        nick = user.strip().split('!')[0]
        print "privmsg: user %s, nick %s, channel %s, msg %s" % \
            (user, nick, channel, msg)

        # Ignore my own messages
        if nick == self.nickname:
            return []

        # Snub private messages
        if channel == self.nickname:
            msg = "It isn't nice to whisper! Play nice with the group."
            return [(nick, msg)]

        for regexp, handler in self.rules:
            m = re.match(regexp, msg)
            if m:
                args = m.groups()
                response = handler(nick, channel, *args)
                if type(response) != list:
                    response = [response]
                return response

        return []

    def getRules(self):
        rules = [
            ('^\s*(?:@BOTNAME@:)?\s*lock\((.*)\)$',   self.lock),
            ('^\s*lock(?:\s.*)?$',                    self.malformedlock),
            ('^\s*(?:@BOTNAME@:)?\s*unlock\((.*)\)$', self.unlock),
            ('^\s*unlock(?:\s.*)?$',                  self.malformedunlock),
            ('@BOTNAME@:\s*status\s*$',               self.status),
            ('@BOTNAME@:.*',                          self.defaulthandler),
        ]
        return rules

    def lock(self, nick, channel, resource):
        if resource in self.locks.keys():
            owner = self.locks[resource]
            return (channel,
                    "%s: DENIED, %s is already locked by %s" %
                    (nick, resource, owner))
        else:
            self.locks[resource] = nick
            return (channel,
                    "%s: GRANTED, %s's lock is all yours now" % 
                    (nick, resource))

    def malformedlock(self, nick, channel):
        messages = [
            (channel, "%s: where you trying to lock a resource?" % nick),
            (channel, "%s: if so, try \"lock(<RESOURCE>)\" instead" % nick)
            ]
        return messages

    def unlock(self, nick, channel, resource):
        if resource not in self.locks.keys():
            return (channel,
                    "%s: ERROR, %s is already free" % 
                    (nick, resource))
        else:
            del self.locks[resource]
            return (channel,
                    "%s: RELEASED, %s lock is free" %
                    (nick, resource))
        
    def malformedunlock(self, nick, channel):
        messages = [
            (channel, "%s: where you trying to unlock a resource?" % nick),
            (channel, "%s: if so, try \"unlock(<RESOURCE>)\" instead" % nick)
            ]
        return messages

    def status(self, nick, channel):
        if len(self.locks) == 0:
            return (channel, "%s: There are no locked resources" % nick)
        else:
            messages  = []
            messages += [(channel, "%s: Status of locked resources:" % nick)]
            messages += [(channel, " resource:%s owner:%s" % (k,v))
                         for k,v in self.locks.items()]
            return messages

    def defaulthandler(self, nick, channel):
        return (channel, "%s: Unrecognized command" % nick)

