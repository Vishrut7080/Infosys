#!/usr/bin/env python3
"""Seed the development database with test users and activity.

Run from the repo root with the virtualenv active:

    python scripts/seed_db.py

This script is safe to run multiple times; it will skip users that already exist.
"""
from app.database.database import (
    init_db, init_admin_db, create_user, add_admin, log_session,
    log_activity, generate_pins, store_pins, get_user_by_email
)


def seed():
    init_db()
    init_admin_db()

    users = [
        {
            'name': 'Alice Admin',
            'email': 'alice@example.com',
            'password': 'password123',
            'secret_audio': 'open sesame',
            'gmail_address': 'alice.test@gmail.com',
            'gmail_app_pass': 'app-pass-1',
            'tg_api_id': '111111',
            'tg_api_hash': 'hash-alice',
            'tg_phone': '+15550000001'
        },
        {
            'name': 'Bob User',
            'email': 'bob@example.com',
            'password': 'password123',
            'secret_audio': 'hello bob',
            'gmail_address': '',
            'gmail_app_pass': '',
            'tg_api_id': '',
            'tg_api_hash': '',
            'tg_phone': ''
        },
        {
            'name': 'Carol Tester',
            'email': 'carol@example.com',
            'password': 'password123',
            'secret_audio': '',
            'gmail_address': 'carol.test@gmail.com',
            'gmail_app_pass': 'app-pass-2',
            'tg_api_id': '123456',
            'tg_api_hash': 'hash-abc',
            'tg_phone': '+15550001111'
        }
    ]

    for u in users:
        existing = get_user_by_email(u['email'])
        if existing:
            print(f"[seed] User exists: {u['email']}")
            continue

        ok, msg = create_user(
            u['name'], u['email'], u['password'], u['secret_audio'],
            u['gmail_address'], u['gmail_app_pass'], u['tg_api_id'], u['tg_api_hash'], u['tg_phone']
        )
        print(f"[seed] Create {u['email']}: {ok} - {msg}")

        # generate and store PINs for users with gmail/telegram
        tg_included = bool(u['tg_api_id'] and u['tg_api_hash'])
        pins = generate_pins(tg_included=tg_included)
        gmail_pin = pins.get('gmail_pin')
        tg_pin = pins.get('telegram_pin')
        if gmail_pin or tg_pin:
            ok2, msg2 = store_pins(u['email'], str(gmail_pin), str(tg_pin) if tg_pin else None)
            print(f"[seed] Store PINs for {u['email']}: {ok2} - {msg2}")
            if gmail_pin:
                print(f"       Gmail PIN: {gmail_pin}")
            if tg_pin:
                print(f"       Telegram PIN: {tg_pin}")

    # make Alice an admin
    ok_admin, admin_msg = add_admin('alice@example.com')
    print(f"[seed] Add admin alice@example.com: {ok_admin} - {admin_msg}")

    # log sessions and sample activities
    for e in ['alice@example.com', 'bob@example.com', 'carol@example.com']:
        try:
            log_session(e, force_insert=True)
            log_activity(e, 'login', 'seed-script')
            log_activity(e, 'voice_command', 'seed voice command example')
        except Exception as ex:
            print(f"[seed] Error logging activity for {e}: {ex}")

    print('[seed] Seeding complete.')


if __name__ == '__main__':
    seed()
