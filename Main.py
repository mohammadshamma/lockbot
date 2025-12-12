import sys, configparser
import argparse
import os
from twisted.internet import reactor, ssl
from LockBot import LockBotFactory

def parse_args():
    parser = argparse.ArgumentParser(description="LockBot IRC Bot")
    parser.add_argument("config", help="Path to configuration file")
    parser.add_argument("--daemonize", "-d", action="store_true", help="Run in background as daemon")
    return parser.parse_args()

def daemonize():
    if os.fork():
        sys.exit()
    os.setsid()
    if os.fork():
        sys.exit()
    sys.stdout.flush()
    sys.stderr.flush()
    with open('/dev/null', 'r') as f:
        os.dup2(f.fileno(), sys.stdin.fileno())
    with open('/dev/null', 'a+') as f:
        os.dup2(f.fileno(), sys.stdout.fileno())
        os.dup2(f.fileno(), sys.stderr.fileno())

if __name__ == "__main__":
    args = parse_args()

    if args.daemonize:
        daemonize()

    cfgpath = args.config

    section='lockbot'
    defaultcfg = {'usessl'  : 'no',
                  'nickname': 'lockbot'}

    cfg = configparser.RawConfigParser(defaultcfg)
    cfg.read(cfgpath)
    
    try:
        usessl = cfg.getboolean(section, 'usessl')

        server   = cfg.get(section, 'server')
        port     = cfg.getint(section, 'port')
        channel  = cfg.get(section, 'channel')
        nickname = cfg.get(section, 'nickname')
        dbdir    = cfg.get(section, 'dbdir')
        password = cfg.get(section, 'password')
    except (configparser.NoSectionError, configparser.NoOptionError) as e:
        sys.stderr.write(f"Configuration error: {e}\n")
        sys.exit(1)

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
