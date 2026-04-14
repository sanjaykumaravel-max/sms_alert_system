"""Create default roles and an admin user in the local DB.

Usage:
    python scripts/create_admin.py --username admin --password secret

If password is omitted the script will prompt interactively.
"""
import argparse
from getpass import getpass
from src.db import init_db, get_session, Role, User
from werkzeug.security import generate_password_hash


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--username', '-u', default='admin')
    parser.add_argument('--password', '-p', help='Password for admin (prompt if omitted)')
    args = parser.parse_args()

    pw = args.password
    if not pw:
        pw = getpass('Admin password: ')
        pw2 = getpass('Confirm password: ')
        if pw != pw2:
            print('Passwords do not match')
            return

    init_db()
    sess = get_session()
    try:
        # create roles if missing
        admin_role = sess.query(Role).filter(Role.name == 'admin').one_or_none()
        user_role = sess.query(Role).filter(Role.name == 'user').one_or_none()
        if not admin_role:
            admin_role = Role(name='admin', description='Administrator')
            sess.add(admin_role)
        if not user_role:
            user_role = Role(name='user', description='Standard user')
            sess.add(user_role)
        sess.commit()

        # create or update admin user
        u = sess.query(User).filter(User.username == args.username).one_or_none()
        if not u:
            u = User(username=args.username, display_name=args.username, hashed_password=generate_password_hash(pw))
            sess.add(u)
            sess.commit()
        else:
            u.hashed_password = generate_password_hash(pw)
            sess.add(u)
            sess.commit()

        # associate admin role
        # Using raw insert into association table for simplicity
        if admin_role and u:
            # ensure role assigned
            if admin_role not in getattr(u, 'roles', []):
                try:
                    u.roles.append(admin_role)
                    sess.add(u)
                    sess.commit()
                except Exception:
                    sess.rollback()

        print('Admin user created/updated:', args.username)
    finally:
        sess.close()


if __name__ == '__main__':
    main()
