from flask import Flask, session
from flask_socketio import SocketIO, join_room
from authlib.integrations.flask_client import OAuth
from werkzeug.middleware.proxy_fix import ProxyFix
from app.core.config import settings

socketio = SocketIO(async_mode='threading')
oauth = OAuth()


@socketio.on('connect')
def _on_ws_connect():
    """Join the user's private room so emit(room=email) reaches this socket."""
    email = session.get('user', {}).get('email')
    if email:
        join_room(email)

def create_app():
    app = Flask(__name__, template_folder='templates', static_folder='static')
    app.secret_key = settings.FLASK_SECRET_KEY
    # Trust X-Forwarded-Proto/Host from Render's HTTPS reverse proxy so that
    # url_for(..., _external=True) generates https:// URLs for OAuth callbacks.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

    # Ensure DB tables exist (idempotent — safe to call on every startup)
    from app.database.database import init_db, init_tasks_db
    init_db()
    init_tasks_db()

    # Initialize extensions
    socketio.init_app(app, cors_allowed_origins="*")
    oauth.init_app(app)

    # Register Google OAuth provider
    oauth.register(
        name='google',
        client_id=settings.GOOGLE_CLIENT_ID,
        client_secret=settings.GOOGLE_CLIENT_SECRET,
        server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
        client_kwargs={'scope': 'openid email profile https://www.googleapis.com/auth/gmail.modify'},
    )

    # Register blueprints
    from app.web.routes.auth import auth_bp
    from app.web.routes.assistant import assistant_bp
    from app.web.routes.admin import admin_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(assistant_bp)
    app.register_blueprint(admin_bp)

    return app
