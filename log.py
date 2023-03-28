import logging
import os


def get_logger():
    service_logger = logging.getLogger('analytics nttm')
    format_ = logging.Formatter('%(asctime)s:%(levelname)s:%(name)s:file %(module)s line %(lineno)d:%(message)s')

    # File log
    file_name = os.path.dirname(__file__) + "/history.log"
    f_handler = logging.FileHandler(file_name)
    f_handler.setLevel(logging.INFO)
    f_handler.setFormatter(format_)
    service_logger.botlog_filename = file_name
    service_logger.addHandler(f_handler)

    # Console log
    c_handler = logging.StreamHandler()
    c_handler.setLevel(logging.DEBUG)
    c_format = logging.Formatter('%(name)s - %(levelname)s - file %(module)s line %(lineno)d - %(message)s')
    c_handler.setFormatter(c_format)
    service_logger.addHandler(c_handler)
    return service_logger


logger = get_logger()
