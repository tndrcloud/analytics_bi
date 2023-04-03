import logging
import os


def get_logger():
    connector_logger = logging.getLogger('connector_nttm')
    format_ = logging.Formatter('%(asctime)s:%(levelname)s:%(name)s:file %(module)s line %(lineno)d:%(message)s')

    # File log
    f_handler = logging.FileHandler('history.log')
    f_handler.setLevel(logging.INFO)
    f_handler.setFormatter(format_)
    connector_logger.addHandler(f_handler)

    # Console log
    c_handler = logging.StreamHandler()
    c_handler.setLevel(logging.DEBUG)
    c_format = logging.Formatter('%(name)s - %(levelname)s - file %(module)s line %(lineno)d - %(message)s')
    c_handler.setFormatter(c_format)
    connector_logger.addHandler(c_handler)
    connector_logger.setLevel(logging.DEBUG)
    return connector_logger


logger = get_logger()

