import sys
from twisted.internet import reactor
from LockBot import LockBotFactory

if __name__ == "__main__":
    chan = sys.argv[1]
    reactor.connectTCP('irc.freenode.net', 6667, LockBotFactory('#' + chan))
    reactor.run()
