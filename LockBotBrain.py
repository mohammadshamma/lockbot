import re
import os
from dbm import dumb
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

class Lock(object):
    def __init__(self, db, name, lockstr=b''): # name is str, lockstr is bytes from db
        self.db = db
        self.name = name # Should be string
        self.lockstr = lockstr.decode('utf-8') if isinstance(lockstr, bytes) else lockstr

        owner, waiters = self.fromstr(self.lockstr)
        self._owner = owner
        self._waiters = waiters

    @property
    def owner(self):
        return self._owner

    @owner.setter
    def owner(self, owner):
        self._owner = owner
        self.sync()

    @property
    def waiters(self):
        return self._waiters

    def wait(self, waiter):
        if waiter not in self._waiters:
            self._waiters.append(waiter)
        self.sync()

    def popwaiter(self, waiter=None):
        if not self._waiters:
            return None
        if not waiter:
            waiter = self._waiters.pop(0)
        else:
            self._waiters.remove(waiter)
        self.sync()

        return waiter

    def fromstr(self, lockstr): # lockstr is string
        if not lockstr:
            return '', []
        flds = lockstr.split(',')

        return flds[0], flds[1:] # owner and waiters are strings

    def tostr(self): # Returns string
        return ','.join([self.owner] + self._waiters) # owner and waiters must be strings

    def sync(self):
        # self.name is string, needs to be encoded for db key
        # self.tostr() returns string, dbm will encode it for value
        self.db[self.name.encode('utf-8')] = self.tostr()

class LockDB(object):
    def __init__(self, path):
        # path is string, DBNAME is string. dumb.open takes string path.
        self.db = dumb.open(path)

    def add(self, name): # name is string
        # Lock expects name as string. Lock.sync() will handle encoding for db.
        self[name] = Lock(self.db, name) # Lock __init__ gets string name, empty lockstr

    def keys(self): # Returns list of strings
        return [k.decode('utf-8') for k in self.db.keys()]

    def items(self): # Returns list of (str, Lock) tuples
        # k is bytes, v is bytes from db
        return [(k.decode('utf-8'), Lock(self.db, k.decode('utf-8'), v))
                for k, v in self.db.items()]

    def __iter__(self): # Should iterate over string keys
        for k in self.db.keys():
            yield k.decode('utf-8')

    def __len__(self):
        return len(self.db.keys()) # Underlying db length

    def __getitem__(self, name): # name is string
        # Fetch from db using encoded name. Lock expects string name and bytes lockstr.
        return Lock(self.db, name, self.db[name.encode('utf-8')])

    def __setitem__(self, name, lock): # name is string, lock is Lock instance
        # lock.sync() is responsible for writing to db with encoded key
        # This explicit __setitem__ might be redundant if Lock.sync() is always used.
        # However, direct assignment like self.locks[key] = new_lock might use this.
        # Ensure Lock.name is string, Lock.tostr() is string.
        self.db[name.encode('utf-8')] = lock.tostr()


    def __delitem__(self, name): # name is string
        del self.db[name.encode('utf-8')]

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
        # The placeholder @BOTNAME@ in rules is meant to be replaced by the fully qualified mention, e.g., "@testbot"
        mention_name = '@' + nickname 
        for rule in rules:
            irule = (rule[0].replace('@BOTNAME@', mention_name),
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
                # Strip whitespace from all captured arguments
                args = [arg.strip() for arg in m.groups()]
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
            ('^\s*(?:@BOTNAME@:)?\s*trylock\((.*)\)$',  self.lock),
            ('^\s*(?:@BOTNAME@:)?\s*trylock\s+(.*)$',   self.lock),
            ('^\s*(?:@BOTNAME@:)?\s*unlock\((.*)\)$',   self.unlock),
            ('^\s*(?:@BOTNAME@:)?\s*unlock\s+(.*)$',    self.unlock),
            ('@BOTNAME@:\s*assignlock\((.*?),(.*)\)$',  self.assignlock),
            ('@BOTNAME@:\s*assignlock\s+(.*)\s+(.*)$',  self.assignlock),
            ('@BOTNAME@:\s*freelock\((.*)\)$',          self.freelock),
            ('@BOTNAME@:\s*freelock\s+(.*)$',           self.freelock),
            ('^\s*(?:@BOTNAME@:)?\s*lock\((.*)\)$',     self.waitlock),
            ('^\s*(?:@BOTNAME@:)?\s*lock\s+(.*)$',      self.waitlock),
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

    def getlock(self, name): # name is string
        # self.locks is LockDB. Iterating it or calling keys() gives strings.
        if name in self.locks: # checks if string `name` is in string keys
            return name

        # Levenshtein.ratio needs two strings. self.locks.keys() now returns strings.
        ratios = [(Levenshtein.ratio(name, l), l) for l in self.locks.keys()]
        best = max(ratios)

        if best[0] < 0.5 or len([c for c in ratios if c[0] == best[0]]) > 1:
            return name

        return best[1]

    def splitResources(self, resourcestr): # resourcestr is string
        results = [i.strip() for i in resourcestr.split(',')] # results are strings
        if '' in results:
            # self.verb might be None if processPrivMsg hasn't set it for this path yet
            current_verb = self.verb if self.verb else "processing"
            raise LockBotException('ERROR: empty resource names are not allowed',
                                   resourcestr, current_verb)
        if len(results) != len(set(results)):
            current_verb = self.verb if self.verb else "processing"
            raise LockBotException('ERROR: duplicate resource name',
                                   resourcestr, current_verb)
        return results, len(results) > 1 # results are list of strings

    def getlocks(self, resourcestr): # resourcestr is string
        resources, multi = self.splitResources(resourcestr) # resources are list of strings
        resources = [self.getlock(r) for r in resources] # r is string, self.getlock returns string
        for r_name in resources: # r_name is string
            # self.locks (LockDB) __contains__ will check string keys
            if r_name not in self.locks:
                raise LockBotException('ERROR: unrecognized resource "%s"' % r_name,
                                       resourcestr, self.verb)

        return resources, multi # resources are list of strings

    def _lock(self, caller, assignee, resourcestr, wait=False): # caller, assignee, resourcestr are strings
        if not assignee: # Disallow empty string assignee
            raise LockBotException("ERROR: assignee cannot be empty", resourcestr, self.verb if self.verb else "locking")
        
        resources, multi = self.getlocks(resourcestr) # resources are list of strings
        waiters = []
        # iterate over all resources once to check for errors
        for r in resources:
            # self.locks[r] returns a Lock instance. Lock.owner should be string.
            # r is string.
            lock_instance = self.locks[r] # r is string, __getitem__ handles it
            if lock_instance.owner == assignee: # assignee is string
                raise LockBotException("%s already hold the lock for resource %s" %
                                       ('you' if lock_instance.owner == caller else assignee, r),
                                       resourcestr, self.verb)
            elif lock_instance.owner and lock_instance.owner != assignee:
                if wait:
                    waiters.append(r) # r is string
                else:
                    raise LockBotException("DENIED, %s is already locked by %s" %
                                           (r, lock_instance.owner), resourcestr, self.verb)

        # all clear, perform lock
        owned = [] # list of strings
        for r in resources: # r is string
            if r in waiters: # waiters contains strings
                self.locks[r].wait(assignee) # assignee is string
            else:
                self.locks[r].owner = assignee # assignee is string
                owned.append(r)
        msg = ''
        if owned: # owned contains strings
            if caller == assignee: # caller, assignee are strings
                own = "you own"
            else:
                own = assignee + " owns" # string concatenation
            msg = "%s: GRANTED, %s %s" %  (caller, own, ', '.join(owned)) # All strings
            if waiters: # waiters contains strings
                msg += " (still waiting for %s)" % ', '.join(waiters)
        elif waiters: # waiters contains strings
            wmsg = [self.lockstatus(w) for w in waiters] # w is string
            msg = '%s: WAITING for %s' % (caller, ', '.join(wmsg)) # All strings

        return msg # msg is string

    def lockstatus(self, name): # name is string
        lock = self.locks[name] # name is string, __getitem__ handles it
        status = ''
        # Lock attributes (owner, waiters) should be strings
        if lock.owner:
            status = 'owner: ' + lock.owner
        if lock.waiters:
            status += ' waiters: ' + ','.join(lock.waiters) # waiters are strings
        if status:
            return '%s (%s)' % (name, status) # name is string

        return name # name is string

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
            self.locks.add(r)
        return (channel,
            "%s: registered resource%s %s" %
                (nick,
                 's' if multi else '',
                 ', '.join(resources)))

    def unregister(self, nick, channel, resourcestr):
        """remove a resource from the database"""
        resources, multi = self.getlocks(resourcestr)
        for r in resources:
            lock_instance = self.locks[r]
            if lock_instance.owner: # Check if there is an actual owner
                raise LockBotException('ERROR, resource "%s" is locked by %s' %
                                       (r, lock_instance.owner), # Use lock_instance.owner for msg
                                       resourcestr, self.verb)
            # If you want to prevent unregistering a resource that has waiters, add:
            # elif lock_instance.waiters:
            #     raise LockBotException('ERROR, resource "%s" has waiters and cannot be unregistered' % r, 
            #                            resourcestr, self.verb)


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
            l = self.locks[r]
            if not l.owner:
                raise LockBotException("%s is already free" % r, resourcestr,
                                       self.verb)
            elif l.owner != nick and nick not in l.waiters:
                raise LockBotException("DENIED, %s holds the lock on %s" %
                                       (self.locks[r].owner, r),
                                       resourcestr, self.verb)

        # all clear, perform unlock
        owned = [r for r in resources if self.locks[r].owner == nick]
        waiters = [r for r in resources if nick in self.locks[r].waiters]
        msgs = []
        if owned:
            multi = len(owned) > 1
            msgs = ["%s: RELEASED, resource%s %s %s free" % (nick,
                                                             's' if multi else '',
                                                             ', '.join(owned),
                                                             'are' if multi else 'is',
                                                             )]
            for r in owned:
                lock = self.locks[r]
                lock.owner = ''
                assignee = lock.popwaiter()
                if assignee:
                    msgs += [self._lock(assignee, assignee, r)]

        if waiters:
            multi = len(owned) > 1
            msgs = ["%s: GAVE UP, no longer waiting for resource%s %s" % (nick,
                                                             's' if multi else '',
                                                             ', '.join(waiters)
                                                             )]
            for r in waiters:
                self.locks[r].popwaiter(nick)

        return [(channel, msg) for msg in msgs]

    def assignlock(self, nick, channel, resourcestr, assignee): # Swapped resourcestr and assignee
        """assign a resource lock to someone else other than the caller"""
        return (channel, self._lock(nick, assignee, resourcestr))

    def freelock(self, nick, channel, resourcestr):
        """release a resource lock even if the caller does not hold the lock (USE WITH CAUTION)"""
        resources, multi = self.getlocks(resourcestr)
        # iterate over all resources once to check for errors
        for r in resources:
            if not self.locks[r].owner:
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
            l = self.locks[r]
            lockowner = l.owner
            l.owner = ''
            msgs += [(channel,
                      "%s: your lock on %s has been released by %s" %
                      (lockowner, r, nick))]
            assignee = l.popwaiter()
            if assignee:
                msgs += [(channel, self._lock(nick, assignee, r))]

        return msgs

    def waitlock(self, nick, channel, resourcestr):
        """try to take the lock, or get on queue if it is currently locked"""
        return (channel, self._lock(nick, nick, resourcestr, wait=True))

    def status(self, nick, channel):
        """list locked resources and their owners"""
        lockeditems = sorted([item[0] for item in self.locks.items() if item[1].owner])
        if len(lockeditems) == 0:
            return (channel, "There are no locked resources")
        else:
            messages  = []
            messages += [(channel, "Status of locked resources:")]
            for k in lockeditems:
                l = self.locks[k]
                msg = "  resource: %s owner: %s" % (k, l.owner)
                if l.waiters:
                    msg += " waiters: %s" % ','.join(l.waiters)
                messages += [(channel, msg)]

            return messages

    def listfree(self, nick, channel):
        """list unlocked resources"""
        freeitems = [item[0] for item in self.locks.items() if not item[1].owner]
        if len(freeitems) == 0:
            return (channel, "There are no unlocked resources")
        else:
            return (channel, "Unlocked resources: " + ', '.join(sorted(freeitems)))

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
            
            args_list = getCmdArguments(handler)
            cmd_args_str = ' '.join(["<%s>" % arg for arg in args_list])
            cmdpart_key = handler.__name__
            if cmd_args_str: # Add space only if there are arguments
                cmdpart_key += ' ' + cmd_args_str
                
            helpTuples.append((cmdpart_key, handler.__doc__))

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
                     "%s: Unrecognized command, try '@%s: help'" % (nick, self.nickname))]
        return messages
