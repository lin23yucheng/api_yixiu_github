# -*- coding: UTF-8 -*-
import os
import logging
import time

#

"""[输出控制]
class LogLevel:
    DEBUG = 0
    LOW = 1
    MIDDLE = 2
    HIGH = 3
    HIGHER = 4
    TOP = 5
"""


class LogLevel:
    DEBUG = 0
    LOW = 1
    MIDDLE = 2
    HIGH = 3
    HIGHER = 4
    TOP = 5


# 日志文件输出等级
logFileLv = LogLevel.LOW
# 日志面板输出等级
logPrintLv = LogLevel.DEBUG

# 初始化Log控件信息
logger = logging.getLogger('Logging')
logger.setLevel(level=logging.DEBUG)
formatter = logging.Formatter('%(message)s')
console = logging.StreamHandler()
console.setFormatter(formatter)
console.setLevel(logging.DEBUG)
logger.addHandler(console)


def get_now(time_format="%Y-%m-%d %H:%M:%S"):
    """获得当前时间的字符串
    精确到毫秒
    """
    nowTime = time.time() * 1000
    now = time.strftime(time_format, time.localtime(
        nowTime / 1000)) + "," + "%03d" % (nowTime % 1000)
    return now


class LogType:
    """日志类型枚举"""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"
    LOGIC = "LOGIC"  # 业务逻辑日志


def logFileHandler(obj, filename, is_split):
    # 项目路径
    prj_path = os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))  # 当前文件的上一级的上一级目录（增加一级）
    if is_split:
        date, s_time = get_now().split(" ")
        hour = s_time.split(":")[0]
        if filename is None:
            filename = hour
        log_path = prj_path + "/log/{0}".format(date)
    else:
        if filename is None:
            filename = "log"
        log_path = prj_path + "/log/"
    if not os.path.exists(log_path):
        os.makedirs(log_path)
    log_name = log_path + "/{filename}.log".format(filename=filename)
    with open(log_name, 'a+') as f:
        f.write(obj + "\n")


def printl(obj, color_code):
    # 字体样式拼装
    colorstr = "{0}{1}{2}".format(color_code[2], obj, "\033[0m")
    string = "%s" % colorstr
    getattr(logger, color_code[0])(string)


def log(message: str, log_type: str = LogType.INFO, is_split: bool = True):
    """
    记录日志

    :param message: 日志消息
    :param log_type: 日志类型 (LogType)
    :param is_split: 是否分割长消息
    """
    if is_split and len(message) > 100:
        # 分割长消息
        parts = [message[i:i + 100] for i in range(0, len(message), 100)]
        for i, part in enumerate(parts):
            print(f"[{log_type}] Part {i + 1}/{len(parts)}: {part}")
    else:
        print(f"[{log_type}] {message}")


class Log(object):
    pass


if __name__ == "__main__":
    print("请确认现在在调试")
    log(1111, LogType.WARNING)
