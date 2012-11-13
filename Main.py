import sys, ConfigParser
from twisted.internet import reactor, ssl
from LockBot import LockBotFactory

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print "You should pass only one argument (configuration path)"
        sys.exit(1)
    cfgpath = sys.argv[1]

    section='lockbot'
    defaultcfg = {'usessl'  : 'no',
                  'nickname': 'lockbot'}

    cfg = ConfigParser.RawConfigParser(defaultcfg)
    cfg.read(cfgpath)
    
    usessl = cfg.getboolean(section, 'usessl')

    server   = cfg.get(section, 'server')
    port     = cfg.getint(section, 'port')
    channel  = cfg.get(section, 'channel')
    nickname = cfg.get(section, 'nickname')
    dbdir    = cfg.get(section, 'dbdir')
    password = cfg.get(section, 'password')

    lockbotfactory = LockBotFactory('#' + channel,
                                    nickname,
                                    dbdir,
                                    password=password)

    connectfn = reactor.connectTCP
    connectargs = []
    connectargs.append(server)
    connectargs.append(port)
    connectargs.append(lockbotfactory)
    if usessl:
        connectfn = reactor.connectSSL
        connectargs.append(ssl.ClientContextFactory())

    connectargs = tuple(connectargs)

    connectfn(*connectargs)
    reactor.run()
