import os
import sys
from datetime import datetime
from typing import List, Dict

import streamlit as st
import pandas as pd

# ---- Load .env early
try:
    from dotenv import load_dotenv
    load_dotenv(override=True)
except Exception:
    pass

# ---- Import project modules
# Prefer the split version (agent.py). If you still use chatbot.py, switch imports accordingly.
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
try:
    # Split structure
    from agent import DatabaseChatBot, get_database_schema, execute_sql_query
except Exception:
    # Legacy single-file fallback
    from chatbot import DatabaseChatBot, get_database_schema, execute_sql_query  # type: ignore

# ---- Helpers
DML_PREFIXES = ("insert", "update", "delete", "drop", "alter", "create", "truncate")

def is_dml(sql: str) -> bool:
    sql = (sql or "").strip().lower()
    return sql.startswith(DML_PREFIXES)

def run_sql(sql: str) -> List[Dict]:
    """
    Execute SQL using the tool interface.
    NOTE: our tools are decorated with @tool, so we call `.invoke(...)`.
    """
    try:
        return execute_sql_query.invoke(sql)
    except Exception as e:
        return [{"error": f"Error executing query: {e}"}]

def get_schema_text() -> str:
    try:
        return get_database_schema.invoke("")
    except Exception as e:
        return f"-- Failed to load schema: {e}"

# ---- Streamlit Page Config
st.set_page_config(
    page_title="Database Chatbot",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---- Styles
st.markdown(
    """
<style>
.main { padding-top: 1rem; }
.user-message {
    background-color: #e3f2fd;
    padding: 0.8rem;
    border-radius: 10px;
    margin: 0.4rem 0;
    text-align: right;
}
.bot-message {
    background-color: #f1f8e9;
    padding: 0.8rem;
    border-radius: 10px;
    margin: 0.4rem 0;
}
.sql-query {
    background-color: #fff3e0;
    padding: 0.5rem;
    border-radius: 6px;
    border-left: 4px solid #ff9800;
    font-family: 'Courier New', monospace;
    margin: 0.5rem 0;
}
</style>
""",
    unsafe_allow_html=True,
)

# ---- Title
st.title("🤖 Smart Database Chatbot")
st.markdown("_Ask in natural English/Arabic and get SQL + results as a table._")

# ---- Session state
if "chatbot" not in st.session_state:
    st.session_state.chatbot = DatabaseChatBot()

if "messages" not in st.session_state:
    st.session_state.messages = []

if "last_sql" not in st.session_state:
    st.session_state.last_sql = ""

if "last_rows" not in st.session_state:
    st.session_state.last_rows = []

# ---- Sidebar
with st.sidebar:
    st.header("📊 Database Info")

    with st.expander("🗂️ Schema"):
        schema = get_schema_text()
        st.code(schema, language="sql")

    st.subheader("📈 Quick Stats")
    try:
        # All these use the tool via .invoke
        customers_count = run_sql("SELECT COUNT(*) AS count FROM customers")
        products_count  = run_sql("SELECT COUNT(*) AS count FROM products")
        orders_count    = run_sql("SELECT COUNT(*) AS count FROM orders")
        total_sales     = run_sql("SELECT SUM(total_amount) AS total FROM orders")

        c = customers_count[0].get("count") if customers_count and isinstance(customers_count[0], dict) else None
        p = products_count[0].get("count") if products_count and isinstance(products_count[0], dict) else None
        o = orders_count[0].get("count") if orders_count and isinstance(orders_count[0], dict) else None
        t = total_sales[0].get("total") if total_sales and isinstance(total_sales[0], dict) else None

        st.metric("Customers", c if c is not None else "-")
        st.metric("Products", p if p is not None else "-")
        st.metric("Orders", o if o is not None else "-")
        if t is not None:
            try:
                st.metric("Total Sales", f"{float(t):,.0f}")
            except Exception:
                st.metric("Total Sales", str(t))
        else:
            st.metric("Total Sales", "-")
    except Exception as e:
        st.error(f"Stats error: {e}")

    st.subheader("💡 Examples")
    examples = [
        "How many customers do we have?",
        "List all customers in Cairo with their registration_date.",
        "Show top 3 most expensive products.",
        "Total sales per city.",
        "Orders from March 2024.",
        "Which customer spent the most?"
    ]
    for q in examples:
        if st.button(q, key=f"ex_{abs(hash(q))}"):
            st.session_state.messages.append({"role": "user", "content": q})
            try:
                reply = st.session_state.chatbot.chat(q)
                st.session_state.messages.append({"role": "assistant", "content": reply})
                # Save last SQL to show rows
                history = st.session_state.chatbot.get_chat_history()
                if history:
                    st.session_state.last_sql = history[-1].get("sql_query", "")
                    # For safety, don't auto-run DML queries
                    if st.session_state.last_sql and not is_dml(st.session_state.last_sql):
                        st.session_state.last_rows = run_sql(st.session_state.last_sql)
                st.rerun()
            except Exception as e:
                st.error(f"Error: {e}")

    if st.button("🗑️ Clear Chat"):
        st.session_state.messages = []
        st.session_state.last_sql = ""
        st.session_state.last_rows = []
        st.session_state.chatbot.clear_history()
        st.rerun()

# ---- Chat area
st.subheader("💬 Conversation")

for m in st.session_state.messages:
    if m["role"] == "user":
        st.markdown(f'<div class="user-message">👤 You: {m["content"]}</div>', unsafe_allow_html=True)
    else:
        st.markdown(f'<div class="bot-message">🤖 Assistant: {m["content"]}</div>', unsafe_allow_html=True)

# ---- Input
user_input = st.chat_input("Type your question...")

if user_input:
    st.session_state.messages.append({"role": "user", "content": user_input})
    st.markdown(f'<div class="user-message">👤 You: {user_input}</div>', unsafe_allow_html=True)

    with st.spinner("Thinking..."):
        try:
            reply = st.session_state.chatbot.chat(user_input)
            st.session_state.messages.append({"role": "assistant", "content": reply})
            st.markdown(f'<div class="bot-message">🤖 Assistant: {reply}</div>', unsafe_allow_html=True)

            # Grab SQL from history and show table
            history = st.session_state.chatbot.get_chat_history()
            if history:
                last = history[-1]
                sql = last.get("sql_query", "") or ""
                st.session_state.last_sql = sql

                if sql:
                    with st.expander("🔍 Executed SQL"):
                        st.code(sql, language="sql")

                    # Do NOT auto-run DML from UI
                    if is_dml(sql):
                        st.warning("This is a write (DML) statement. It will not be auto-executed from the UI.")
                        st.session_state.last_rows = []
                    else:
                        rows = run_sql(sql)
                        st.session_state.last_rows = rows

                        # Display rows nicely
                        if rows and isinstance(rows, list) and isinstance(rows[0], dict) and "error" not in rows[0]:
                            try:
                                df = pd.DataFrame(rows)
                                st.dataframe(df, use_container_width=True)
                                st.caption(f"Returned rows: {len(df)}")
                            except Exception:
                                st.write(rows)
                        elif rows and "error" in rows[0]:
                            st.error(rows[0]["error"])
                        else:
                            st.info("No rows returned.")
            st.rerun()
        except Exception as e:
            st.error(f"❌ Error: {e}")
            st.info("Make sure GROQ_API_KEY is set in your .env")

# ---- Detailed history
with st.expander("📋 Detailed Chat History"):
    hist = st.session_state.chatbot.get_chat_history()
    if hist:
        for i, entry in enumerate(reversed(hist)):
            st.markdown(f"**Turn {len(hist) - i}** — {entry['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}")
            st.markdown(f"👤 **Question:** {entry['user']}")
            st.markdown(f"🤖 **Answer:** {entry['bot']}")
            if entry.get("sql_query"):
                st.code(entry["sql_query"], language="sql")
            st.divider()
    else:
        st.info("No history yet.")

st.markdown("---")
st.markdown(
    """
**How to use**
1) Type your question in English/Arabic  
2) See the generated SQL and results table  
3) Use sidebar examples to try quickly

**Tech**
- LangGraph
- Groq LLM
- SQLite
- Streamlit
"""
)

if __name__ == "__main__":
    st.info("💡 Tip: ensure GROQ_API_KEY is present in your .env before running.")
