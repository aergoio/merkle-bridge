import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

stream_formatter = logging.Formatter('%(message)s')

stream_handler = logging.StreamHandler()
stream_handler.setFormatter(stream_formatter)

logger.addHandler(stream_handler)
