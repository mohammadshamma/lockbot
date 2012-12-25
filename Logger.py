import logging
import logging.handlers

class Logger(object):

    _instance = None
    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(Logger, cls).__new__(cls, *args, **kwargs)
        return cls._instance
        
    def __init__(self):
        self.logger = logging.getLogger()
        self.logger.setLevel(logging.DEBUG)

        handler = logging.handlers.SysLogHandler(address='/dev/log')

        self.logger.addHandler(handler)

    def debug(self, msg):
        self.logger.debug('[lockbot] debug: ' + msg)

    def critical(self, msg):
        self.logger.critical('[lockbot] critical: ' + msg)

    def info(self, msg):
        self.logger.info('[lockbot] info: ' + msg)

