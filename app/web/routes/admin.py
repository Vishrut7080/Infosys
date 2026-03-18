from flask import Blueprint, render_template, jsonify, request, session
from app.database import database
from app.web import socketio
from app.web.utils import admin_required

admin_bp = Blueprint('admin', __name__)

def emit_stats():
    users = database.get_all_users()
    socketio.emit('stats_update', {
        'total_users': len(users), 
        'active_users': len(database.get_active_users(minutes=30)), 
        'total_admins': sum(1 for u in users if u['is_admin']), 
        'total_commands': database.get_activity_count_global('voice_command'), 
        'total_logins': database.get_activity_count_global('login'), 
        'emails_sent': database.get_activity_count_global('email_sent'), 
        'tg_sent': database.get_activity_count_global('telegram_sent'), 
        'wa_sent': database.get_activity_count_global('whatsapp_sent')
    })

@admin_bp.route('/admin')
@admin_required
def admin_page():
    return render_template('admin.html', user=session['user'])

@admin_bp.route('/admin/users')
@admin_required
def admin_get_users():
    return jsonify({'users': database.get_all_users()})

@admin_bp.route('/admin/active-users')
@admin_required
def admin_active_users():
    minutes = int(request.args.get('minutes', 30))
    active = database.get_active_users(minutes=minutes)
    return jsonify({'active_users': active})

@admin_bp.route('/admin/activity')
@admin_required
def admin_get_activity():
    return jsonify({
        'log': database.get_activity_log(
            email=request.args.get('email'), 
            action=request.args.get('action'), 
            limit=int(request.args.get('limit', 100))
        )
    })

@admin_bp.route('/admin/delete-user', methods=['POST'])
@admin_required
def admin_delete_user():
    email = request.get_json().get('email', '')
    if email == session['user'].get('email', ''): 
        return jsonify({'status': 'error', 'message': "You can't delete your own account."})
    success, msg = database.admin_delete_user(email)
    if success: emit_stats()
    return jsonify({'status': 'success' if success else 'error', 'message': msg})

@admin_bp.route('/admin/add-admin', methods=['POST'])
@admin_required
def admin_add_admin():
    success, msg = database.add_admin(request.get_json().get('email', ''))
    if success: emit_stats()
    return jsonify({'status': 'success' if success else 'error', 'message': msg})

@admin_bp.route('/admin/remove-admin', methods=['POST'])
@admin_required
def admin_remove_admin():
    email = request.get_json().get('email', '')
    if email == session['user'].get('email', ''): 
        return jsonify({'status': 'error', 'message': "You can't remove your own admin access."})
    success, msg = database.remove_admin(email)
    if success: emit_stats()
    return jsonify({'status': 'success' if success else 'error', 'message': msg})


# ─── Missing admin routes that the admin JS depends on ─────────

@admin_bp.route('/admin/stats')
@admin_required
def admin_stats():
    users = database.get_all_users()
    return jsonify({
        'total_users': len(users),
        'active_users': len(database.get_active_users(minutes=30)),
        'total_admins': sum(1 for u in users if u['is_admin']),
        'total_commands': database.get_activity_count_global('voice_command'),
        'total_logins': database.get_activity_count_global('login'),
        'emails_sent': database.get_activity_count_global('email_sent'),
        'tg_sent': database.get_activity_count_global('telegram_sent'),
        'wa_sent': database.get_activity_count_global('whatsapp_sent'),
        'pin_fails': database.get_activity_count_global('pin_failed'),
    })


@admin_bp.route('/admin/api-usage')
@admin_required
def admin_api_usage():
    actions = [
        'login', 'logout', 'voice_command', 'email_read', 'email_sent',
        'telegram_sent', 'telegram_received', 'pin_failed', 'whatsapp_sent',
    ]
    usage = {}
    for action in actions:
        count = database.get_activity_count_global(action)
        if count > 0:
            usage[action] = count
    return jsonify({'usage': usage})


@admin_bp.route('/admin/error-logs')
@admin_required
def admin_error_logs():
    errors = database.get_activity_log(action='error', limit=200)
    return jsonify({'errors': errors})
