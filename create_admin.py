# Run once: python create_admin.py
from Backend.database import init_db, add_admin

init_db()

email = input('Enter email to grant admin access: ').strip()
success, msg = add_admin(email)
print(msg)
print(f'Now visit http://localhost:5000/admin while logged in as {email}')