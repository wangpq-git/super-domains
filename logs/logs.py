# 日志输出格式
import logging
from logging import handlers


class Logger(object):
    level_relations = {
        'debug': logging.DEBUG,
        'info': logging.INFO,
        'warning': logging.WARNING,
        'error': logging.ERROR,
        'crit': logging.CRITICAL
    }  # 日志级别关系映射

    def __init__(self, filename, level='info', when='D', backCount=7,
                 fmt='%(asctime)s %(levelname)s %(pathname)s %(funcName)s %(message)s',
                 datefmt='%a, %d %b %Y %H:%M:%S'):
        self.logger = logging.getLogger(filename)

        if not self.logger.hasHandlers():  # 检查是否已经有处理器
            format_str = logging.Formatter(fmt, datefmt)  # 设置日志格式
            self.logger.setLevel(self.level_relations.get(level))  # 设置日志级别

            # 设置屏幕输出处理器
            sh = logging.StreamHandler()
            sh.setFormatter(format_str)

            # 设置文件输出处理器
            th = handlers.TimedRotatingFileHandler(
                filename=filename, when=when, backupCount=backCount, encoding='utf-8'
            )
            th.setFormatter(format_str)

            # 添加处理器
            self.logger.addHandler(sh)
            self.logger.addHandler(th)
