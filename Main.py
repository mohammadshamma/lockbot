import sys
from twisted.internet import reactor, ssl
from LockBot import LockBotFactory

if __name__ == "__main__":
    chan = sys.argv[1]
    reactor.connectTCP('localhost', 6667, LockBotFactory('#' + chan))
    # reactor.connectSSL('localhost', 6668, LockBotFactory('#' + chan),
    #                    ssl.ClientContextFactory())
    reactor.run()
