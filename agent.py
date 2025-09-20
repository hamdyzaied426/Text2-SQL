import os
from datetime import datetime
from typing import TypedDict, List, Dict, Any, Optional
from langgraph.graph import StateGraph, START, END, MessagesState
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

# our utils/tools
from db_utils import (
    get_database_schema,
    execute_sql_query,
    validate_sql_query,
    as_markdown_table,
    as_row_details,
    ensure_aliases,
    clean_code_fences,
)
from dotenv import load_dotenv
load_dotenv(override=True)


# -------- LLM setup --------
MODEL_NAME   = os.getenv("MODEL_NAME", "openai/gpt-oss-120b")
TEMPERATURE  = float(os.getenv("MODEL_TEMPERATURE", "0.1"))
MAX_TOKENS   = int(os.getenv("MAX_TOKENS", "1000"))
llm = ChatGroq(model=MODEL_NAME, temperature=TEMPERATURE, max_tokens=MAX_TOKENS)

# -------- States --------
class MsgState(MessagesState):
    sql_query: Optional[str]
    query_result: Optional[List[Dict]]
    final_response: Optional[str]

class ChatBotState(TypedDict):
    user_query: str
    sql_query: Optional[str]
    query_result: Optional[List[Dict]]
    final_response: Optional[str]

# -------- Nodes (classic) --------
def query_analyzer_node(state: ChatBotState) -> ChatBotState:
    user_query = state.get("user_query", "") or ""
    if not user_query:
        return {**state, "sql_query": "", "query_result": [], "final_response": "Please provide a question in the user_query field."}

    schema = get_database_schema.invoke("")

    system_prompt = f"""
You are a database expert for SQLite.

Database schema:
{schema}

Rules:
1) Use exact table/column names from the schema.
2) Valid SQLite syntax only.
3) Use JOINs when needed to link tables.
4) If the user asks for multiple actions (e.g., delete then show), output multiple statements separated by semicolons ';'.
5) Do NOT include explanations, output SQL only.
6) When using aggregations (COUNT/SUM/AVG/MIN/MAX), add a short alias (e.g., COUNT(*) AS count).

Examples:
Q: Delete Mona Ahmed then show customers.
A: DELETE FROM customers WHERE name = 'Mona Ahmed'; SELECT * FROM customers;

Q: How many customers?
A: SELECT COUNT(*) AS count FROM customers;

User question: {user_query}

Write the SQL (one or more statements separated by ';') only:
"""
    response  = llm.invoke([SystemMessage(content=system_prompt), HumanMessage(content=user_query)])
    sql_query = ensure_aliases(clean_code_fences(response.content))
    return {**state, "sql_query": sql_query, "query_result": [], "final_response": ""}

def query_executor_node(state: ChatBotState) -> ChatBotState:
    sql_query = (state.get("sql_query") or "").strip()
    if not sql_query:
        return {**state, "query_result": [{"error": "No SQL query provided"}], "final_response": ""}

    valid = validate_sql_query.invoke(sql_query)
    if not valid.get("valid"):
        fixed = ensure_aliases(sql_query)
        if fixed != sql_query:
            sql_query = fixed
            valid = validate_sql_query.invoke(sql_query)

    if not valid.get("valid"):
        return {**state, "query_result": [{"error": f"Invalid query: {valid.get('error')}"}], "final_response": ""}

    result = execute_sql_query.invoke(sql_query)
    return {**state, "query_result": result, "final_response": ""}

def response_generator_node(state: ChatBotState) -> ChatBotState:
    sql_query    = (state.get("sql_query") or "").strip()
    query_result = state.get("query_result", []) or []

    if query_result and isinstance(query_result, list) and "error" in query_result[0]:
        return {**state, "final_response": f"❌ Error: {query_result[0]['error']}"}

    # Non-SELECT summary
    if query_result and isinstance(query_result[0], dict) and "rows_affected" in query_result[0]:
        ra = query_result[0].get("rows_affected", 0)
        lr = query_result[0].get("last_row_id", None)
        body = (
            f"**SQL**\n```sql\n{sql_query}\n```\n"
            f"**Result**\n- Rows affected: **{ra}**\n- Last inserted id: **{lr}**"
        )
        return {**state, "final_response": body}

    # SELECT: full table + details
    rows_count = len(query_result)
    table_md   = as_markdown_table(query_result, max_rows=1000)
    details_md = as_row_details(query_result, max_rows=100)
    body = (
        f"**SQL**\n```sql\n{sql_query}\n```\n"
        f"**Rows:** {rows_count}\n\n"
        f"{table_md}\n\n"
        f"{details_md}"
    )
    return {**state, "final_response": body}

# -------- Nodes (messages) --------
def _extract_last_user_message(state: MsgState) -> str:
    for m in reversed(state["messages"]):
        if getattr(m, "type", None) == "human" or getattr(m, "role", None) == "user":
            return getattr(m, "content", "")
        if isinstance(m, dict) and (m.get("type") == "human" or m.get("role") == "user"):
            return m.get("content", "")
    return ""

def query_analyzer_node_msgs(state: MsgState) -> MsgState:
    user_query = _extract_last_user_message(state)
    if not user_query:
        final = "Please type your question."
        return {**state, "final_response": final, "sql_query": "", "query_result": [], "messages": [AIMessage(final)]}

    schema = get_database_schema.invoke("")
    system_prompt = f"""
You are a database expert. Convert the user's question into ONE valid SQL query.

Database schema:
{schema}

Rules:
1) Use exact table/column names from the schema.
2) Valid SQL only.
3) Use JOINs when needed to link tables.
4) Output ONE SQL query only, no explanation.
5) When using aggregations (COUNT/SUM/AVG/MIN/MAX), ALWAYS add a short alias.

User question: {user_query}

Write SQL query only:
"""
    response  = llm.invoke([SystemMessage(content=system_prompt), HumanMessage(content=user_query)])
    sql_query = ensure_aliases(clean_code_fences(response.content))
    return {**state, "sql_query": sql_query}

def query_executor_node_msgs(state: MsgState) -> MsgState:
    sql_query = (state.get("sql_query") or "").strip()
    if not sql_query:
        return {**state, "query_result": [{"error": "No SQL query provided"}]}

    valid = validate_sql_query.invoke(sql_query)
    if not valid.get("valid"):
        fixed = ensure_aliases(sql_query)
        if fixed != sql_query:
            sql_query = fixed
            valid = validate_sql_query.invoke(sql_query)

    if not valid.get("valid"):
        return {**state, "query_result": [{"error": f"Invalid query: {valid.get('error')}"}]}
    return {**state, "query_result": execute_sql_query.invoke(sql_query)}

def response_generator_node_msgs(state: MsgState) -> MsgState:
    sql_query    = (state.get("sql_query") or "").strip()
    query_result = state.get("query_result") or []

    if query_result and isinstance(query_result, list) and "error" in query_result[0]:
        final = f"❌ Error: {query_result[0]['error']}"
        return {**state, "final_response": final, "messages": [AIMessage(content=final)]}

    if query_result and isinstance(query_result[0], dict) and "rows_affected" in query_result[0]:
        ra = query_result[0].get("rows_affected", 0)
        lr = query_result[0].get("last_row_id", None)
        final = (
            f"**SQL**\n```sql\n{sql_query}\n```\n"
            f"**Result**\n- Rows affected: **{ra}**\n- Last inserted id: **{lr}**"
        )
        return {**state, "final_response": final, "messages": [AIMessage(content=final)]}

    rows_count = len(query_result)
    table_md   = as_markdown_table(query_result, max_rows=1000)
    details_md = as_row_details(query_result, max_rows=100)
    final = (
        f"**SQL**\n```sql\n{sql_query}\n```\n"
        f"**Rows:** {rows_count}\n\n"
        f"{table_md}\n\n"
        f"{details_md}"
    )
    return {**state, "final_response": final, "messages": [AIMessage(content=final)]}

# -------- Graph builders --------
def create_chatbot_graph():
    workflow = StateGraph(ChatBotState)
    workflow.add_node("query_analyzer",     query_analyzer_node)
    workflow.add_node("query_executor",     query_executor_node)
    workflow.add_node("response_generator", response_generator_node)
    workflow.add_edge(START, "query_analyzer")
    workflow.add_edge("query_analyzer", "query_executor")
    workflow.add_edge("query_executor", "response_generator")
    workflow.add_edge("response_generator", END)
    return workflow.compile()

def create_chatbot_graph_messages():
    wf = StateGraph(MsgState)
    wf.add_node("query_analyzer",     query_analyzer_node_msgs)
    wf.add_node("query_executor",     query_executor_node_msgs)
    wf.add_node("response_generator", response_generator_node_msgs)
    wf.add_edge(START, "query_analyzer")
    wf.add_edge("query_analyzer", "query_executor")
    wf.add_edge("query_executor", "response_generator")
    wf.add_edge("response_generator", END)
    return wf.compile()

# -------- Simple CLI (optional) --------
class DatabaseChatBot:
    def __init__(self):
        self.graph = create_chatbot_graph()
        self.chat_history: List[Dict[str, Any]] = []

    def chat(self, user_input: str) -> str:
        initial_state: ChatBotState = {
            "user_query": user_input,
            "sql_query": "",
            "query_result": [],
            "final_response": "",
        }
        result = self.graph.invoke(initial_state)
        self.chat_history.append({
            "user": user_input,
            "bot": result.get("final_response", ""),
            "sql_query": result.get("sql_query", ""),
            "timestamp": datetime.now(),
        })
        return result.get("final_response", "")

    def get_chat_history(self):
        return self.chat_history

    def clear_history(self):
        self.chat_history = []

if __name__ == "__main__":
    print("🤖 Database chatbot — type 'exit' to quit.")
    bot = DatabaseChatBot()
    while True:
        q = input("You: ").strip()
        if q.lower() in ["exit", "quit"]:
            break
        print(bot.chat(q))
