# 🤖 Smart Database Chatbot — Documentation

An AI-powered chatbot that lets you query a relational database in plain English/Arabic, built with **LangGraph**, **Groq LLM**, and **SQLite**. The bot can translate a natural-language question into SQL, validate it, execute it, and return both a **human-friendly explanation** and the **raw tabular results**.

---

## ✨ Features

- **Natural-language to SQL** (English & Arabic).
- **SQL validation** before execution (uses `EXPLAIN QUERY PLAN`).
- **Safe execution**: blocks multi-statement injection; supports one statement per request.
- **Two outputs**:
  1) Friendly summary/explanation  
  2) Raw table with columns/rows returned from the database
- **LangGraph workflows**:
  - `database_chatbot`: classic state inputs/outputs
  - `database_chatbot_chat`: message-based graph for LangGraph Studio “Chat” tab
- **Streamlit app** for quick UI.
- **Sample SQLite schema** (customers, products, orders) seeded automatically.
- **Configurable via `.env`**.

---

## 🧱 Architecture

```
User → (LLM: Query Analyzer) → SQL
     → (Validator) → (Executor) → Rows
     → (LLM: Response Generator) → Summary
```

- **Query Analyzer**: Converts the user question to a single, valid SQL statement using the database schema.
- **Validator**: Runs `EXPLAIN QUERY PLAN` to catch syntax and structural issues.
- **Executor**: Executes the **single** SQL statement and returns rows as a list of dicts.
- **Response Generator**: Explains the results in plain language and includes helpful hints (e.g., scalar answers).

Graphs:
- **`database_chatbot`** → classic graph (good for programmatic calls).
- **`database_chatbot_chat`** → messages-state graph (enables “Chat” tab in LangGraph Studio).

---

## 📦 Project Structure

```
database-chatbot/
├── agent.py                 # Graph nodes, tools, and LLM wiring (LangGraph/Groq)
├── database.py              # Database bootstrap & helpers (SQLite schema + seed)
├── app.py                   # Streamlit UI (optional)
├── chatbot.py               # Legacy/CLI runner (optional)
├── langgraph.json           # Graph registry for LangGraph Studio (2 graphs)
├── requirements.txt         # Python dependencies
├── .env                     # Your environment variables (not committed)
└── README.md                # This documentation
```

> If you still have a single-file version, you can keep using it, but the split (`agent.py` / `database.py`) is recommended for clarity and reuse.

---

## ⚙️ Requirements

- Python **3.9+**
- A **Groq API key**

---

## 🚀 Quick Start

### 1) Create and activate a virtual environment
```bash
python -m venv venv
# Windows
venv\Scripts\activate
# macOS / Linux
source venv/bin/activate
```

### 2) Install dependencies
```bash
pip install -r requirements.txt
```

### 3) Configure environment variables

Create `.env` (or copy from `.env.example`) and fill in:

```
GROQ_API_KEY=your_actual_groq_key
DATABASE_PATH=company_db.sqlite
MODEL_NAME=llama-3.1-8b-instant
MODEL_TEMPERATURE=0.1
MAX_TOKENS=1000
```

> `agent.py` calls `load_dotenv(override=True)` so values in `.env` are loaded at runtime.

### 4) Run with LangGraph Studio (recommended)

```bash
pip install "langgraph-cli[inmem]"
langgraph dev --allow-blocking
```

Open the printed Studio URL.  
You’ll see two graphs registered from `langgraph.json`:

- `database_chatbot`
- `database_chatbot_chat` (messages graph for chat)

**Enable the Chat tab**:

1. In Studio, click **Manage Assistants** → **Create Assistant**.  
2. Choose the **`database_chatbot_chat`** graph (the one backed by `MessagesState`).  
3. Save. Now the **Chat** tab will be available for that graph.

### 5) Run the Streamlit UI (optional)

```bash
streamlit run app.py
```

### 6) Run from CLI (optional)

```bash
python chatbot.py
```

---

## 🗄️ Sample Database

Created automatically at startup (if not present):

**customers**
- `id` (INTEGER, PK)
- `name` (TEXT)
- `email` (TEXT, UNIQUE)
- `phone` (TEXT)
- `city` (TEXT)
- `registration_date` (DATE)

**products**
- `id` (INTEGER, PK)
- `name` (TEXT)
- `category` (TEXT)
- `price` (DECIMAL)
- `stock_quantity` (INTEGER)

**orders**
- `id` (INTEGER, PK)
- `customer_id` (INTEGER, FK → customers.id)
- `product_id` (INTEGER, FK → products.id)
- `quantity` (INTEGER)
- `order_date` (DATE)
- `total_amount` (DECIMAL)

Seed data includes 4 customers, several products, and orders.

---

## 🧠 How the LLM is Prompted

The query analyzer is instructed to:
- Use **exact** table/column names.
- Produce **one** valid SQL statement.
- Add **aliases** for aggregations:
  - `COUNT(*) AS count`, `SUM(x) AS total`, `AVG(x) AS average`, etc.
- Use `JOIN`s when linking tables.

The response generator:
- Returns a clear explanation.
- Mentions **number of rows**.
- Provides the **scalar answer** explicitly if the result is a one-cell result.
- Never replaces the **raw rows**; the raw rows are also returned and displayed.

---

## 🧑‍💻 Usage Examples

Ask the bot:

- “How many customers do we have?”
- “List all customers in Cairo with their registration dates.”
- “Show top 3 most expensive products.”
- “Total sales per city.”
- “Orders from March 2024.”
- “Which customer spent the most?”
- “What products are available in ‘Electronics’?”

**DML (write) queries** (e.g., `DELETE`, `UPDATE`, `INSERT`) are **discouraged by default**. If you allow them, the executor still supports **one statement per request** for safety. The validator and executor will block multiple statements (e.g., `DELETE; SELECT ...`) to avoid injection.

---

## 🔒 Safety & Best Practices

- **One statement only**: the executor enforces a single SQL statement per run.
- **Validation**: `EXPLAIN QUERY PLAN` is used to catch parsing/structure issues before execution.
- **No secrets in code**: keep the `GROQ_API_KEY` in `.env`, never in source files.
- **DML caution**: If you must allow `DELETE/UPDATE/INSERT`, consider a confirmation layer or a role-based flag.

---

## 🛠️ Configuration

- **Model**: change `MODEL_NAME`, `MODEL_TEMPERATURE`, `MAX_TOKENS` in `.env`.
- **Database path**: set `DATABASE_PATH` to target a specific SQLite file.
- **LLM provider**: code uses `langchain-groq`’s `ChatGroq`; you can swap for another LLM if needed.

---

## 🧪 Troubleshooting

### “GroqError: The api_key client option must be set…”
- Ensure `.env` exists and contains `GROQ_API_KEY`.
- Make sure `agent.py` calls `load_dotenv(override=True)`.
- On Windows PowerShell, you can test:
  ```powershell
  $env:GROQ_API_KEY
  ```
  If it’s empty, set it or use `.env`.

### “You can only execute one statement at a time”
- SQLite executes a **single** statement per call. Don’t chain statements like `DELETE ...; SELECT ...`.  
  Instead, run two separate turns:
  1) Ask: “Delete Mona Ahmed from customers.”  
  2) Then ask: “Show me all customers.”  
  (If you really need multi-step operations in one turn, implement a workflow that orchestrates two executions.)

### “near 'DELETE': syntax error”
- The LLM may generate `DELETE` against a wrong table/column or without a `WHERE`.  
  Try rephrasing: “Delete the customer whose name is ‘Mona Ahmed’ from **customers** table.”

### “Chat tab is disabled in Studio”
- You must bind an **Assistant** to a **messages graph** (`database_chatbot_chat`).  
  Use **Manage Assistants → Create Assistant → pick `database_chatbot_chat`**.

### “No rows returned”
- Confirm the filter actually matches the seed data.
- Run a broader query first (e.g., `SELECT * FROM customers;`) to see available values.

---

## 🔧 Extending the Bot

- **Add tables/columns**: update `database.py` (schema + seed) and restart.
- **Switch to Postgres/MySQL**: replace the SQLite connection layer; keep tool interfaces identical.
- **Add guardrails**: whitelist statements, block DML entirely, or add a review/confirm step.
- **Richer UI**: extend `app.py` to display pagination, CSV export, or charts.

---

## 📜 License

MIT (see `LICENSE`, if included in your repo).

---

## 🙌 Acknowledgements

Built with ❤️ using **LangGraph** and **Groq**.
