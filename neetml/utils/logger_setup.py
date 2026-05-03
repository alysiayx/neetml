import logging
import colorlog
import sys
import os
from typing import Union
from pathlib import Path

from .constants import LOGS_DIR

_LEVEL_MAP = {
    "CRITICAL": logging.CRITICAL,
    "ERROR": logging.ERROR,
    "WARNING": logging.WARNING,
    "INFO": logging.INFO,
    "DEBUG": logging.DEBUG,
    "NOTSET": logging.NOTSET,
}

def get_log_level(env_var: str = "NEETML_LOG_LEVEL", default: str = "INFO") -> int:
    value = os.getenv(env_var, default).upper().strip()
    return _LEVEL_MAP.get(value, _LEVEL_MAP[default])

# Configure colorlog with bold fonts
handler = colorlog.StreamHandler()
# handler = colorlog.StreamHandler(stream=sys.stdout)  # Direct log messages to stdout
default_format = '%(log_color)s%(asctime)s - %(levelname)s - %(message)s'
simple_format = '%(log_color)s%(message)s'

default_formatter = colorlog.ColoredFormatter(
    default_format,
    log_colors={
        'DEBUG': 'bold_cyan',
        'INFO': 'bold_green',
        'WARNING': 'bold_yellow',
        'ERROR': 'bold_red',
        'CRITICAL': 'bold_red',
    },
    style='%', 
    # datefmt='%Y-%m-%d %H:%M:%S', # exclude milliseconds
    datefmt='%Y-%m-%d %H:%M' # exclude seconds and milliseconds
)

simple_formatter = colorlog.ColoredFormatter(
    simple_format,
    log_colors={
        'DEBUG': 'bold_cyan',
        'INFO': 'bold_green',
        'WARNING': 'bold_yellow',
        'ERROR': 'bold_red',
        'CRITICAL': 'bold_red',
    },
    style='%'
)

def get_logger(name: str = "logs", log_dir: Union[str, Path, None] = None) -> logging.Logger:
    
    level = get_log_level()
    
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger  

    logger.setLevel(level)

    console_handler = colorlog.StreamHandler(sys.stdout)
    console_handler.setFormatter(default_formatter)
    logger.addHandler(console_handler)

    log_path = Path(log_dir) if log_dir else LOGS_DIR
    log_path.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(log_path / f"{name}.log", encoding="utf-8")
    file_handler.setFormatter(default_formatter)
    logger.addHandler(file_handler)

    return logger

def _with_temp_formatter(logger: logging.Logger, temp_formatter: logging.Formatter, fn):
    """Swap all handler formatters temporarily, run fn(), then restore."""
    handlers = list(logger.handlers)
    old_formatters = [h.formatter for h in handlers]
    try:
        for h in handlers:
            h.setFormatter(temp_formatter)
        fn()
    finally:
        for h, old in zip(handlers, old_formatters):
            h.setFormatter(old)

def log_with_border(logger: logging.Logger, message: str):
    border_length = len(message) + 4
    border = "+" + "-" * border_length + "+"
    def _emit():
        logger.info(f"\n{border}\n|  {message}  |\n{border}\n")
    _with_temp_formatter(logger, simple_formatter, _emit)

def log_line_break(logger: logging.Logger):
    def _emit():
        logger.info("\n" + "*" * 50 + "\n")
    _with_temp_formatter(logger, simple_formatter, _emit)