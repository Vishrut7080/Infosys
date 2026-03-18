import logging
import sys

def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            # Add a file handler if you want persistent logs:
            # logging.FileHandler('app.log')
        ]
    )
    # Reduce noise from Telethon
    logging.getLogger('telethon').setLevel(logging.WARNING)

logger = logging.getLogger("infosys")
