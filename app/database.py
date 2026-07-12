import os
import sys
from pathlib import Path

import mysql.connector
from mysql.connector.connection import MySQLConnection

BASE_DIR = Path(__file__).resolve().parent.parent

MYSQL_HOST = os.environ.get("MYSQL_HOST", "localhost")
MYSQL_PORT = int(os.environ.get("MYSQL_PORT", "3306"))
MYSQL_USER = os.environ.get("MYSQL_USER", "root")
MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD", "")
MYSQL_DATABASE = os.environ.get("MYSQL_DATABASE", "fund_screener")

def _database_exists() -> bool:
    conn = mysql.connector.connect(
        host=MYSQL_HOST, port=MYSQL_PORT, user=MYSQL_USER, password=MYSQL_PASSWORD
    )
    cur = conn.cursor()
    cur.execute("SHOW DATABASES LIKE %s", (MYSQL_DATABASE,))
    exists = cur.fetchone() is not None
    cur.close()
    conn.close()
    return exists


if not _database_exists():
    sys.path.insert(0, str(BASE_DIR / "scripts"))# add scripts dir to the beginning(0) of search path for importing build_database
    from init_db import build_database  # noqa: E402

    build_database()


def get_connection() -> MySQLConnection:
    return mysql.connector.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DATABASE,
    )
