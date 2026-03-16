from flask import Flask, render_template, request, session, redirect, url_for, jsonify
import pyodbc
import anthropic
import config

app = Flask(__name__)
app.secret_key = config.SECRET_KEY

# --- Database connection ---
def get_db_connection():
    conn = pyodbc.connect(
        f"DRIVER={{ODBC Driver 18 for SQL Server}};"
        f"SERVER={config.DB_SERVER};"
        f"DATABASE={config.DB_NAME};"
        f"UID={config.DB_USER};"
        f"PWD={config.DB_PASSWORD};"
        f"TrustServerCertificate=yes;"
    )
    return conn

# --- Table schema sent to Claude so it knows what to query ---
TABLE_SCHEMA = """
You have access to one table called ReportingInventoryFlat with these columns:
- ESN (nvarchar): unique device identifier / IMEI
- ProjectName (nvarchar): the project the device belongs to
- ProjectTag (nvarchar): project tag or label
- ReceiveDate (datetime): date the device was received
- Product_Place (nvarchar): physical location of the device e.g. 'Product Room'
- Manufacturer (nvarchar): device manufacturer e.g. 'Apple', 'Samsung'
- Model (nvarchar): device model e.g. 'iPhone 14 Pro'
- Colour (nvarchar): device colour
- Grade (nvarchar): device grade
- Received_Grade (nvarchar): grade at time of receiving
- DeviceCost (decimal): cost of the device
- Function_Test_Created (nvarchar): date function test was completed
- Grading_Created (nvarchar): date grading was completed
- LastRefreshed (datetime): when the table was last refreshed

This table contains in-stock devices only. All data is current as of the LastRefreshed timestamp.
"""

SYSTEM_PROMPT = f"""
You are an inventory data assistant. You answer questions by generating a single SQL SELECT query
against the ReportingInventoryFlat table.

{TABLE_SCHEMA}

Rules:
- Only generate SELECT queries. Never use INSERT, UPDATE, DELETE, DROP, or any other write operations.
- Only query the ReportingInventoryFlat table.
- Keep queries simple and efficient.
- Return ONLY the raw SQL query with no explanation, no markdown, no code blocks.
- If the question cannot be answered from this table, respond with: UNABLE_TO_ANSWER
"""

# --- Run SQL query safely ---
def run_query(sql):
    sql = sql.strip()
    # Safety check - only allow SELECT
    if not sql.upper().startswith('SELECT'):
        return None, "Only SELECT queries are allowed."
    # Block dangerous keywords
    blocked = ['INSERT', 'UPDATE', 'DELETE', 'DROP', 'ALTER', 'TRUNCATE', 'EXEC', 'EXECUTE']
    for word in blocked:
        if word in sql.upper():
            return None, f"Query contains forbidden keyword: {word}"
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(sql)
        columns = [col[0] for col in cursor.description]
        rows = cursor.fetchall()
        conn.close()
        return {'columns': columns, 'rows': [list(row) for row in rows]}, None
    except Exception as e:
        return None, str(e)

# --- Ask Claude to generate SQL ---
def generate_sql(user_question):
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    message = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=500,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_question}]
    )
    return message.content[0].text.strip()

# --- Format result into a readable answer ---
def format_answer(sql, data, user_question):
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    rows_preview = str(data['rows'][:50])  # limit to 50 rows for formatting
    message = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=500,
        system="You are a helpful inventory assistant. Given a SQL query result, answer the user's question in plain English. Be concise and direct. If it's a count or sum, state the number clearly.",
        messages=[{
            "role": "user",
            "content": f"Question: {user_question}\nSQL used: {sql}\nColumns: {data['columns']}\nData: {rows_preview}\n\nAnswer the question in plain English."
        }]
    )
    return message.content[0].text.strip()

# --- Routes ---
@app.route('/', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        if (request.form['username'] == config.CHAT_USERNAME and
                request.form['password'] == config.CHAT_PASSWORD):
            session['logged_in'] = True
            return redirect(url_for('chat'))
        else:
            error = 'Invalid username or password.'
    return render_template('login.html', error=error)

@app.route('/chat')
def chat():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    return render_template('chat.html')

@app.route('/ask', methods=['POST'])
def ask():
    if not session.get('logged_in'):
        return jsonify({'error': 'Not logged in'}), 401

    user_question = request.json.get('question', '').strip()
    if not user_question:
        return jsonify({'error': 'No question provided'}), 400

    # Step 1: Generate SQL from question
    sql = generate_sql(user_question)

    if sql == 'UNABLE_TO_ANSWER':
        return jsonify({'answer': "I'm unable to answer that from the inventory data I have access to.", 'sql': ''})

    # Step 2: Run the SQL
    data, error = run_query(sql)
    if error:
        return jsonify({'answer': f'There was an error running the query: {error}', 'sql': sql})

    if not data['rows']:
        return jsonify({'answer': 'No results found for your question.', 'sql': sql})

    # Step 3: Format into plain English answer
    answer = format_answer(sql, data, user_question)
    return jsonify({'answer': answer, 'sql': sql, 'rows': data['rows'][:50], 'columns': data['columns']})

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
