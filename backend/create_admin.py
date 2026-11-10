"""Create an administrator explicitly from a terminal; never through public signup."""

import argparse
import getpass
from auth import hash_password
from database import init_db, get_conn


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("email")
    parser.add_argument("--name", default="Administrator")
    args = parser.parse_args()
    password = getpass.getpass("New administrator password (at least 10 characters): ")
    if len(password) < 10 or password != getpass.getpass("Confirm password: "):
        parser.error("Passwords must match and contain at least 10 characters.")
    init_db()
    with get_conn() as conn:
        if conn.execute(
            "SELECT 1 FROM auth_users WHERE username=?", (args.email.strip().lower(),)
        ).fetchone():
            parser.error("Account already exists; no account was modified.")
        conn.execute(
            "INSERT INTO auth_users(username,password,role,name) VALUES(?,?,?,?)",
            (args.email.strip().lower(), hash_password(password), "admin", args.name),
        )
    print("Administrator created.")


if __name__ == "__main__":
    main()
