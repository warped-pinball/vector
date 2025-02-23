from logger import logger_instance
import machine
log = logger_instance

def datetime_string():
    dt = machine.RTC().datetime()
    return "{0:04d}-{1:02d}-{2:02d} {4:02d}:{5:02d}:{6:02d}".format(*dt)

def enter_log(level, text, log_and_print=False):
    datetime = datetime_string()
    log_entry = "{0} [{1:8}] {2}".format(datetime, level, text)
    if log_and_print:
        log.log(log_entry)        
    else:
        print(log_entry)
  
def info(*items):
    enter_log("info", " ".join(map(str, items)))

def warn(*items):
    enter_log("warning", " ".join(map(str, items)))

def error(*items):
    enter_log("error", " ".join(map(str, items)),True)

def debug(*items):
    enter_log("debug", " ".join(map(str, items)),True)

def exception(*items):
    enter_log("exception", " ".join(map(str, items)),True)
