import logging
import os
from logging.handlers import RotatingFileHandler

LOG_DIR = "/360Pipe/python_services/dev/signatureScraper_service/logs"
os.makedirs(LOG_DIR, exist_ok=True)

formatter = logging.Formatter(
    "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)

file_handler = RotatingFileHandler(
    f"{LOG_DIR}/signatureScraper_service.log",
    maxBytes=10 * 1024 * 1024,
    backupCount=5
)
file_handler.setFormatter(formatter)

console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)

root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)

if not root_logger.handlers:
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)