import os
from app.web import create_app, socketio
from app.core.config import settings
from app.core.logging import setup_logging, logger

# Initialize logging
setup_logging()

# Clean break: Delete old Telegram session files on startup
if not settings.mock_telegram:
    try:
        from app.services.telegram import delete_all_session_files, cleanup_stale_session_files
        # Delete session files older than 1 hour (from previous server runs)
        deleted = delete_all_session_files(max_age_hours=1)
        if deleted > 0:
            logger.info(f"Clean break: Deleted {deleted} old Telegram session files. Users will need to re-authenticate.")
        # Also clean up any remaining stale session files (older than 7 days)
        cleanup_stale_session_files()
    except Exception as e:
        logger.error(f"Error cleaning up Telegram session files: {e}")

app = create_app()

if __name__ == "__main__":
    logger.info(f"Server running at http://{settings.FLASK_HOST}:{settings.FLASK_PORT}")
    socketio.run(app, host=settings.FLASK_HOST, port=settings.FLASK_PORT, debug=settings.FLASK_ENV != 'production')
