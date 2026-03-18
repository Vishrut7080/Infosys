import os
from app.web import create_app, socketio
from app.core.config import settings
from app.core.logging import setup_logging, logger

# Initialize logging
setup_logging()

app = create_app()

if __name__ == "__main__":
    logger.info(f"Server running at http://{settings.FLASK_HOST}:{settings.FLASK_PORT}")
    socketio.run(app, host=settings.FLASK_HOST, port=settings.FLASK_PORT, debug=settings.FLASK_ENV != 'production')
