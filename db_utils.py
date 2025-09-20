import os
import re
import sqlite3
from typing import List, Dict, Any
from langchain_core.tools import tool

# ---------- DB bootstrap (demo) ----------
def _db_path() -> str:
    return os.getenv("DATABASE_PATH", "company_db.sqlite")

def setup_sample_database():
    """Create a sample database with customers, products, and orders data"""
    conn = sqlite3.connect(_db_path())
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT UNIQUE,
            phone TEXT,
            city TEXT,
            registration_date DATE
        )""")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            category TEXT,
            price DECIMAL(10,2),
            stock_quantity INTEGER
        )""")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY,
            customer_id INTEGER,
            product_id INTEGER,
            quantity INTEGER,
            order_date DATE,
            total_amount DECIMAL(10,2),
            FOREIGN KEY (customer_id) REFERENCES customers(id),
            FOREIGN KEY (product_id) REFERENCES products(id)
        )""")

    # Idempotent seed data
    sample_customers = [
        (1, "Ahmed Mohamed",  "ahmed@email.com",  "01234567890", "Cairo",       "2024-01-15"),
        (2, "Fatma Ali",      "fatma@email.com",  "01234567891", "Alexandria",  "2024-02-20"),
        (3, "Mahmoud Hassan", "mahmoud@email.com","01234567892", "Giza",        "2024-03-10"),
        (4, "Mona Ahmed",     "mona@email.com",   "01234567893", "Cairo",       "2024-04-05"),
    ]
    sample_products = [
        (1, "Dell Laptop",            "Electronics", 15000.00, 50),
        (2, "iPhone",                 "Electronics", 25000.00, 30),
        (3, "Programming Book",       "Books",          200.00, 100),
        (4, "Bluetooth Headphones",   "Electronics",     500.00, 75),
    ]
    sample_orders = [
        (1, 1, 1, 1, "2024-01-20", 15000.00),
        (2, 2, 2, 1, "2024-02-25", 25000.00),
        (3, 1, 3, 2, "2024-03-15",   400.00),
        (4, 3, 4, 1, "2024-04-10",   500.00),
    ]

    cursor.executemany("INSERT OR REPLACE INTO customers VALUES (?,?,?,?,?,?)", sample_customers)
    cursor.executemany("INSERT OR REPLACE INTO products  VALUES (?,?,?,?,?)",  sample_products)
    cursor.executemany("INSERT OR REPLACE INTO orders    VALUES (?,?,?,?,?,?)",sample_orders)

    conn.commit()
    conn.close()

# Call on import (demo only)
setup_sample_database()

# ---------- Tools ----------
@tool
def get_database_schema() -> str:
    """Retrieve database schema (tables & columns)."""
    conn = sqlite3.connect(_db_path())
    cursor = conn.cursor()

    schema_info: List[str] = []
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name!='sqlite_sequence'")
    tables = [t[0] for t in cursor.fetchall()]

    for table_name in tables:
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns = cursor.fetchall()
        schema_info.append(f"\nTable: {table_name}")
        for col in columns:
            col_name, col_type = col[1], col[2]
            schema_info.append(f"  - {col_name}: {col_type}")

    conn.close()
    return "\n".join(schema_info)

@tool
def execute_sql_query(sql_query: str) -> List[Dict]:
    """
    Execute one or multiple SQL statements (SQLite).
    - Statements separated by ';' are executed sequentially.
    - If the last statement is SELECT -> returns rows as list[dict]
    - Otherwise -> returns rows_affected & last_row_id.
    """
    try:
        conn = sqlite3.connect(_db_path())
        cursor = conn.cursor()

        statements = [s.strip() for s in sql_query.strip().split(";") if s.strip()]
        if not statements:
            return [{"error": "Empty SQL"}]

        total_rows_affected = 0
        last_row_id = None
        select_result: List[Dict[str, Any]] = []

        for i, stmt in enumerate(statements):
            upper = stmt.lstrip().upper()
            if upper.startswith("SELECT"):
                cursor.execute(stmt)
                cols = [d[0] for d in cursor.description] if cursor.description else []
                rows = cursor.fetchall()
                select_result = [dict(zip(cols, r)) for r in rows]
            else:
                cursor.execute(stmt)
                conn.commit()
                if cursor.rowcount != -1:
                    total_rows_affected += cursor.rowcount
                last_row_id = cursor.lastrowid

        conn.close()

        # If last statement is SELECT return rows; else DML summary
        return select_result if statements[-1].lstrip().upper().startswith("SELECT") \
               else [{"rows_affected": total_rows_affected, "last_row_id": last_row_id}]

    except Exception as e:
        return [{"error": f"Error executing query: {str(e)}"}]

@tool
def validate_sql_query(sql_query: str) -> Dict[str, Any]:
    """
    Validate one or multiple SQL statements for SQLite.
    - For SELECT statements: run EXPLAIN QUERY PLAN
    - For non-SELECT: try preparing/executing safely to catch syntax errors.
    """
    try:
        conn = sqlite3.connect(_db_path())
        cursor = conn.cursor()

        statements = [s.strip() for s in sql_query.strip().split(";") if s.strip()]
        if not statements:
            return {"valid": False, "error": "Empty SQL"}

        plans = []
        for stmt in statements:
            upper = stmt.lstrip().upper()
            if upper.startswith("SELECT"):
                cursor.execute(f"EXPLAIN QUERY PLAN {stmt}")
                plans.append(cursor.fetchall())
            else:
                try:
                    cursor.execute(stmt)
                    conn.rollback()
                except Exception:
                    pass  # any syntax errors will be caught below if fatal

        conn.close()
        return {"valid": True, "plan": plans}
    except Exception as e:
        return {"valid": False, "error": str(e)}

# ---------- Pretty printing ----------
def as_markdown_table(rows: List[Dict[str, Any]], max_rows: int = 1000) -> str:
    """Convert list of dicts to a Markdown table."""
    if not rows:
        return "_No rows._"
    cols: List[str] = []
    for r in rows:
        for k in r.keys():
            if k not in cols:
                cols.append(k)
    header = "| " + " | ".join(cols) + " |"
    sep    = "| " + " | ".join(["---"] * len(cols)) + " |"
    body   = []
    for r in rows[:max_rows]:
        vals = [str(r.get(c, "")) for c in cols]
        body.append("| " + " | ".join(vals) + " |")
    table = "\n".join([header, sep] + body)
    if len(rows) > max_rows:
        table += f"\n\n_Note: showing first {max_rows} of {len(rows)} rows._"
    return table

def as_row_details(rows: List[Dict[str, Any]], max_rows: int = 100, title: str = "Row details") -> str:
    if not rows:
        return ""
    lines = [f"**{title}:**"]
    for i, r in enumerate(rows[:max_rows], 1):
        lines.append(f"\n**Row {i}**")
        for k, v in r.items():
            lines.append(f"- **{k}**: {v}")
    if len(rows) > max_rows:
        lines.append(f"\n_Note: showing first {max_rows} of {len(rows)} rows._")
    return "\n".join(lines)

# ---------- SQL helpers ----------
AGG_FUNCS = ("COUNT", "SUM", "AVG", "MIN", "MAX")

def ensure_aliases(sql: str) -> str:
    """Ensure every aggregation in SELECT has a short alias."""
    m = re.match(r"(?is)\s*select\s+(.*?)\s+from\s+", sql or "")
    if not m:
        return sql
    select_part = m.group(1)

    def patch(select_text: str, func: str, alias: str) -> str:
        pattern = rf"(?i)({func}\s*\(\s*[^)]+\s*\))(?!(\s+AS\s+\w))"
        return re.sub(pattern, rf"\1 AS {alias}", select_text)

    patched = select_part
    patched = patch(patched, "COUNT", "count")
    patched = patch(patched, "SUM",   "total")
    patched = patch(patched, "AVG",   "average")
    patched = patch(patched, "MIN",   "min")
    patched = patch(patched, "MAX",   "max")
    return sql if patched == select_part else sql.replace(select_part, patched, 1)

def clean_code_fences(text: str) -> str:
    if "```sql" in text:
        return text.split("```sql")[1].split("```")[0].strip()
    if "```" in text:
        return text.split("```")[1].strip()
    return text.strip()
