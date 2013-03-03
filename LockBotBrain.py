import re
import os
import dumbdbm

import Logger

DBNAME = 'locks'

class LockBotException(Exception):
    def __init__(self, msg, resourcestr, verb):
        super(LockBotException, self).__init__()
        self.msg = msg
        self.resourcestr = resourcestr
        self.verb = verb

class LockBotBrain(object):

    def __init__(self, nickname, dbdir):

        if not os.path.isdir(dbdir):
            os.mkdir(dbdir)
        dbpath = os.path.join(dbdir, DBNAME)

        self.locks = dumbdbm.open(dbpath)
        self.nickname = nickname
        self.rules = self.interpolateRules(nickname)
        self.logger = Logger.Logger()
        self.verb = None

    def interpolateRules(self, nickname):
        rules = self.getRules()
        irules = []
        for rule in rules:
            irule = (rule[0].replace('@BOTNAME@', nickname),
                     rule[1])
            irules.append(irule)
        return irules

    def getErrorMessages(self, nick, channel, exc):
        if ',' in exc.resourcestr:
            return [(channel, '%s: %s' % (nick, exc.msg)),
                    (channel, "%s: no resources %s" % (nick, exc.verb))]
        else:
            return (channel, exc.msg)

    def processPrivMsg(self, user, channel, msg):

        nick = user.strip().split('!')[0]
        self.logger.debug("privmsg: user %s, nick %s, channel %s, msg %s" % \
                              (user, nick, channel, msg))

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
                self.verb = handler.__name__ + 'ed'
                try:
                    response = handler(nick, channel, *args)
                except LockBotException as exc:
                    response = self.getErrorMessages(nick, channel, exc)
                self.verb = None
                if type(response) != list:
                    response = [response]
                return response

        return []

    def getRules(self):
        rules = [
            ('^\s*(?:@BOTNAME@:)?\s*lock\((.*)\)$',     self.lock),
            ('^\s*(?:@BOTNAME@:)?\s*lock\s+(.*)$',      self.lock),
            ('^\s*(?:@BOTNAME@:)?\s*unlock\((.*)\)$',   self.unlock),
            ('^\s*(?:@BOTNAME@:)?\s*unlock\s+(.*)$',    self.unlock),
            ('@BOTNAME@:\s*freelock\((.*)\)$',          self.freelock),
            ('@BOTNAME@:\s*freelock\s+(.*)$',           self.freelock),
            ('@BOTNAME@:\s*register\((.*)\)$',          self.register),
            ('@BOTNAME@:\s*register\s+(.*)$',           self.register),
            ('@BOTNAME@:\s*unregister\((.*)\)$',        self.unregister),
            ('@BOTNAME@:\s*unregister\s+(.*)$',         self.unregister),
            ('@BOTNAME@:\s*status\s*$',                 self.status),
            ('@BOTNAME@:\s*listlocked\s*$',             self.status),
            ('@BOTNAME@:\s*listfree\s*$',               self.listfree),
            ('@BOTNAME@:\s*list\s*$',                   self.list),
            ('@BOTNAME@:\s*help\s*$',                   self.help),
            ('@BOTNAME@:.*',                            self.defaulthandler),
        ]
        return rules

    def splitResources(self, resourcestr):
        results = [i.strip() for i in resourcestr.split(',')]
        if '' in results:
            raise LockBotException('ERROR: empty resource names are not allowed',
                                   resourcestr, self.verb)
        if len(results) != len(set(results)):
            raise LockBotException('ERROR: duplicate resource name')
        return results, len(results) > 1

    def lock(self, nick, channel, resourcestr):
        resources, multi = self.splitResources(resourcestr)
        # iterate over all resources once to check for errors
        for r in resources:
            if r not in self.locks.keys():
                raise LockBotException('ERROR: unrecognized resource "%s"' % r,
                                       resourcestr, self.verb)
            elif self.locks[r] == nick:
                raise LockBotException("you already hold the lock for resource %s" % r,
                                       resourcestr, self.verb)
            elif self.locks[r] and self.locks[r] != nick:
                raise LockBotException("DENIED, %s is already locked by %s" %
                                       (r, self.locks[r]),
                                       resourcestr, self.verb)

        # all clear, perform lock
        for r in resources:
            self.locks[r] = nick
        return (channel,
                    "%s: GRANTED, resource%s %s %s all yours" %
                    (nick,
                     's' if multi else '',
                     ', '.join(resources),
                     'are' if multi else 'is',
                     ))

    def register(self, nick, channel, resourcestr):
        resources, multi = self.splitResources(resourcestr)
        for r in resources:
            if r in self.locks.keys():
                raise LockBotException('ERROR, resource "%s" is already registered' % r,
                                       resourcestr, self.verb)

        # all clear, register resources
        for r in resources:
            self.locks[r] = ''
        return (channel,
            "%s: registered resource%s %s" %
                (nick,
                 's' if multi else '',
                 ', '.join(resources)))

    def unregister(self, nick, channel, resourcestr):
        resources, multi = self.splitResources(resourcestr)
        for r in resources:
            if r not in self.locks.keys():
                raise LockBotException('ERROR, unrecognized resource "%s"' % r,
                                       resourcestr, self.verb)
            elif self.locks[r]:
                raise LockBotException('ERROR, resource "%s" is locked by %s' %
                                       (r, self.locks[r]),
                                       resourcestr, self.verb)

        # all clear, unregister resources
        for r in resources:
            del self.locks[r]
        return (channel,
            "%s: removed resource%s %s" %
                (nick,
                 's' if multi else '',
                 ', '.join(resources)))

    def unlock(self, nick, channel, resourcestr):
        resources, multi = self.splitResources(resourcestr)
        # iterate over all resources once to check for errors
        for r in resources:
            if r not in self.locks.keys():
                raise LockBotException('ERROR: unrecognized resource "%s"' % r,
                                       resourcestr, self.verb)
            elif self.locks[r] == '':
                raise LockBotException("%s is already free" % r,
                                       resourcestr, self.verb)
            elif self.locks[r] != nick:
                raise LockBotException("DENIED, %s holds the lock on %s" %
                                       (self.locks[r], r),
                                       resourcestr, self.verb)

        # all clear, perform unlock
        for r in resources:
            self.locks[r] = ''
        return (channel,
                    "%s: RELEASED, resource%s %s %s free" %
                    (nick,
                     's' if multi else '',
                     ', '.join(resources),
                     'are' if multi else 'is',
                     ))

    def freelock(self, nick, channel, resourcestr):
        resources, multi = self.splitResources(resourcestr)
        # iterate over all resources once to check for errors
        for r in resources:
            if r not in self.locks.keys():
                raise LockBotException('ERROR: unrecognized resource "%s"' % r,
                                       resourcestr, self.verb)
            if not self.locks[r]:
                raise LockBotException('ERROR: resource %s is already unlocked' % r,
                                       resourcestr, self.verb)

        # all clear, perform freelock
        msgs = [(channel,
                 "%s: RELEASED, resource%s %s %s free" %
                 (nick,
                  's' if multi else '',
                  ', '.join(resources),
                  'are' if multi else 'is',
                  ))]

        for r in resources:
            lockowner = self.locks[r]
            self.locks[r] = ''
            msgs += [(channel,
                      "%s: your lock on %s has been released by %s" %
                      (lockowner, r, nick))]
        return msgs

    def status(self, nick, channel):
        lockeditems = sorted([item[0] for item in self.locks.items() if item[1]])
        if len(lockeditems) == 0:
            return (channel, "There are no locked resources")
        else:
            messages  = []
            messages += [(channel, "Status of locked resources:")]
            messages += [(channel, "  resource:%s owner:%s" % (k, self.locks[k]))
                         for k in lockeditems]
            return messages

    def listfree(self, nick, channel):
        freeitems = [item[0] for item in self.locks.items() if not item[1]]
        if len(freeitems) == 0:
            return (channel, "There are no unlocked resources")
        else:
            return (channel, "Unlocked resources: " + ', '.join(freeitems))

    def list(self, nick, channel):
        if len(self.locks.keys()) == 0:
            return (channel, "There are no registered resources")
        else:
            return (channel, "List of registered resources: %s" %
                    ', '.join(sorted(self.locks.keys())))

    def help(self, nick, channel):
        messages = [
            "List of lockbot commands:",
            " lock <resource>       take hold of a lock on a resource",
            " unlock <resource>     release the resource lock",
            " freelock <resource>   release a resource lock even if the caller",
            "                       does not hold the lock (USE WITH CAUTION)",
            " register <resource>   add a new resource to the database",
            " unregister <resource> remove a resource from the database",
            " status                list locked resources and their owners",
            " listlocked            see \"status\"",
            " listfree              list unlocked resources",
            " list:                 list all registered resources",
            " help:                 display this help message"
            ]
        return [(channel, message) for message in messages]

    def defaulthandler(self, nick, channel):
        messages = [(channel,
                     "%s: Unrecognized command, try '%s: help'" % (nick, self.nickname))]
        return messages
