import re
import os
import dumbdbm
import inspect

import Levenshtein

import Logger

DBNAME = 'locks'

def cleannick(nick):
    return nick.rstrip('_')

class LockBotException(Exception):
    def __init__(self, msg, resourcestr, verb):
        super(LockBotException, self).__init__()
        self.msg = msg
        self.resourcestr = resourcestr
        self.verb = verb

class LockDB(object):
    def __init__(self, path):
        self.db = dumbdbm.open(path)

    def keys(self):
        return self.db.keys()

    def items(self):
        return self.db.items()

    def __iter__(self):
        return self.db.__iter__()

    def __len__(self):
        return len(self.keys())

    def __getitem__(self, name):
        return self.db[name]

    def __setitem__(self, name, val):
        self.db[name] = val

class LockBotBrain(object):

    def __init__(self, nickname, dbdir):

        if not os.path.isdir(dbdir):
            os.mkdir(dbdir)
        dbpath = os.path.join(dbdir, DBNAME)

        self.locks = LockDB(dbpath)
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
        #    msg = "It isn't nice to whisper! Play nice with the group."
        #    return [(nick, msg)]
            msg = '%s: %s' % (self.nickname, msg)
            channel = nick

        for regexp, handler in self.rules:
            m = re.match(regexp, msg)
            if m:
                args = m.groups()
                self.verb = handler.__name__ + 'ed'
                try:
                    response = handler(cleannick(nick), channel, *args)
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
            ('@BOTNAME@:\s*assignlock\((.*?),(.*)\)$',  self.assignlock),
            ('@BOTNAME@:\s*assignlock\s+(.*)\s+(.*)$',  self.assignlock),
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

    def getlock(self, name):
        if name in self.locks:
            return name

        ratios = [(Levenshtein.ratio(name, l), l) for l in self.locks]
        best = max(ratios)

        if best[0] < 0.5 or len([c for c in ratios if c[0] == best[0]]) > 1:
            return name

        return best[1]

    def splitResources(self, resourcestr):
        results = [i.strip() for i in resourcestr.split(',')]
        if '' in results:
            raise LockBotException('ERROR: empty resource names are not allowed',
                                   resourcestr, self.verb)
        if len(results) != len(set(results)):
            raise LockBotException('ERROR: duplicate resource name')
        return results, len(results) > 1

    def getlocks(self, resourcestr):
        resources, multi = self.splitResources(resourcestr)
        resources = [self.getlock(r) for r in resources]
        for r in resources:
            if r not in self.locks:
                raise LockBotException('ERROR: unrecognized resource "%s"' % r,
                                       resourcestr, self.verb)

        return resources, multi

    def _lock(self, caller, assignee, resourcestr):
        resources, multi = self.getlocks(resourcestr)
        # iterate over all resources once to check for errors
        for r in resources:
            if self.locks[r] == assignee:
                raise LockBotException("%s already hold the lock for resource %s" %
                                       ('you' if self.locks[r] == caller else assignee, r),
                                       resourcestr, self.verb)
            elif self.locks[r] and self.locks[r] != assignee:
                raise LockBotException("DENIED, %s is already locked by %s" %
                                       (r, self.locks[r]),
                                       resourcestr, self.verb)

        # all clear, perform lock
        for r in resources:
            self.locks[r] = assignee
        return "%s: GRANTED, resource%s %s %s all yours" %  (assignee,
                                                             's' if multi else '',
                                                             ', '.join(resources),
                                                             'are' if multi else 'is',
                                                             )

    def lock(self, nick, channel, resourcestr):
        """take hold of a lock on a resource"""
        return (channel, self._lock(nick, nick, resourcestr))

    def register(self, nick, channel, resourcestr):
        """add a new resource to the database"""
        resources, multi = self.splitResources(resourcestr)
        for r in resources:
            if r in self.locks:
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
        """remove a resource from the database"""
        resources, multi = self.getlocks(resourcestr)
        for r in resources:
            if self.locks[r]:
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
        """release the resource lock"""
        resources, multi = self.getlocks(resourcestr)
        # iterate over all resources once to check for errors
        for r in resources:
            if self.locks[r] == '':
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

    def assignlock(self, nick, channel, assignee, resourcestr):
        """assign a resource lock to someone else other than the caller"""
        return (channel, self._lock(nick, assignee, resourcestr))

    def freelock(self, nick, channel, resourcestr):
        """release a resource lock even if the caller does not hold the lock (USE WITH CAUTION)"""
        resources, multi = self.getlocks(resourcestr)
        # iterate over all resources once to check for errors
        for r in resources:
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
        """list locked resources and their owners"""
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
        """list unlocked resources"""
        freeitems = [item[0] for item in self.locks.items() if not item[1]]
        if len(freeitems) == 0:
            return (channel, "There are no unlocked resources")
        else:
            return (channel, "Unlocked resources: " + ', '.join(freeitems))

    def list(self, nick, channel):
        """list all registered resources"""
        if len(self.locks.keys()) == 0:
            return (channel, "There are no registered resources")
        else:
            return (channel, "List of registered resources: %s" %
                    ', '.join(sorted(self.locks.keys())))

    def help(self, nick, channel):
        """display this help message"""

        def getCmdArguments(handler):
            return inspect.getargspec(handler)[0][3:]

        helpTuples = []
        rules = self.getRules()
        processedHandlers = set()
        for _, handler in rules:
            if handler in processedHandlers:
                continue
            processedHandlers.add(handler)
            helpTuples.append((handler.__name__ + ' ' +
                               ' '.join(["<%s>" % arg
                                         for arg in getCmdArguments(handler)]),
                               handler.__doc__
                               ))
            if handler.__name__ == 'help':
                break

        padding = max([len(cmdpart) for cmdpart, _ in helpTuples])

        messages = ["List of lockbot commands:"]
        for cmdpart, description in helpTuples:
            message = " %s:%s%s" % (cmdpart,
                                    (padding - len(cmdpart) + 1) * ' ',
                                    description if description else 'N/A')
            messages.append(message)

        return [(channel, message) for message in messages]

    def defaulthandler(self, nick, channel):
        messages = [(channel,
                     "%s: Unrecognized command, try '%s: help'" % (nick, self.nickname))]
        return messages
