# NetAssist: Enterprise Hybrid Intelligence Architecture & Pipeline Specification

This document provides a comprehensive technical breakdown of the **NetAssist** chatbot system (Netsol Technologies Hybrid Intelligence Platform). It covers every file in the repository, the complete **LangGraph** state machine architecture, all nodes, tools, state mutations, conditional edges, self-correction loops, and an end-to-end trace of how a user prompt flows through the system.

---

## 1. Directory Structure & File-by-File Breakdown

```
NetsolChatbot/
├── agent/
│   ├── __init__.py           # Package marker for the agent module
│   ├── state.py              # TypedDict schema defining the graph's global state
│   ├── tools.py              # Security tools: SQL AST validation, safe DB execution, entity matching
│   ├── nodes.py              # LangGraph execution nodes (LLM invocations, retrieval, SQL gen & exec)
│   └── graph.py              # LangGraph workflow definition, node registration, conditional edges
├── api/
│   ├── __init__.py           # Package marker for the API module
│   └── routes.py             # FastAPI REST endpoints (/api/v1/chat, /api/v1/chat/file)
├── core/
│   ├── __init__.py           # Package marker for the core module
│   ├── config.py             # Environment configuration & AppSettings singleton
│   ├── database.py           # SQLite connection pools, table schemas, JSON ingestion, usage logger
│   ├── chromaClient.py       # ChromaDB vector store client, collection configuration, chunk upserts/queries
│   └── llmClient.py          # Gemini API clients, proxy wrappers, cost calculator, exponential backoff retry loop
├── scraper/
│   ├── crawlerUtils.py       # URL domain filtering, path exclusion, semantic text chunking
│   ├── playwrightEngine.py   # Headless Chromium browser context manager, auto-scroll, tab expansion
│   ├── engine.py             # Manual/standalone scraper orchestration
│   └── syncTask.py           # Automatic background delta scraper (SHA-256 hash comparison gatekeeper)
├── utils/
│   └── fileExtractor.py      # Multi-format document parser (.pdf, .docx, .doc, .txt, .md) with size limits
├── static/
│   └── index.html            # Single-page web interface (embedded chat UI frontend)
├── data/
│   ├── companyData.db        # SQLite database storing employee records, scraper hashes, usage logs
│   ├── employeeProfiles.json # Seed JSON dataset for initial database ingestion
│   └── chromaStorage/        # Persistent ChromaDB vector storage directory
├── main.py                   # FastAPI server entry point, lifespan boot/teardown sequence, background scheduler
├── streamlit_app.py          # Streamlit UI host application embedding the custom web component
├── requirements.txt          # Python package dependency specifications
├── commitEmbeddings.py       # Utility script to commit vector embeddings manually
├── runManualScraper.py       # Utility script to launch the scraper on-demand
└── generate_graph_data.py    # Developer utility for generating pipeline visualizers
```

---

### File Details & Responsibilities

#### `main.py`
- **Purpose**: Serves as the primary application entry point using **FastAPI** and **Uvicorn**.
- **How it Works**:
  - Defines an `appLifespan` context manager that runs on server boot and shutdown.
  - On startup: Calls `setupDatabase()`, verifies if `EmployeeProfiles` has data (ingesting `employeeProfiles.json` if empty), initializes **APScheduler** (`AsyncIOScheduler`), and schedules `executeDeltaSync` to run periodically (every 12 hours) as well as immediately on a background thread (`asyncio.to_thread`).
  - Registers the REST router from `api/routes.py` under the `/api/v1` prefix.
  - Mounts the `static/` directory to serve the frontend web interface directly at `/`.

#### `core/config.py`
- **Purpose**: Centralized configuration management via `AppSettings`.
- **How it Works**: Loads environment variables from `.env` using `python-dotenv`. Exposes parameters like `geminiApiKey`, `dbPath`, `chromaStoragePath`, `employeeJsonPath`, `scraperBaseUrl`, `scraperMaxPages`, `syncIntervalHours`, and `chromaCollectionName`. Instantiates a global `settings` object used throughout the application.

#### `core/database.py`
- **Purpose**: SQLite database interface handling schema creation, connection pooling, seed data ingestion, scraper hash storage, and LLM usage logging.
- **How it Works**:
  - `getWriteConnection()`: Provides read-write database connections for backend ingestion and background scrapers.
  - `getReadOnlyConnection()`: **Security Zone 3** — Provides read-only URI connections (`file:path?mode=ro`) to prevent LLM SQL injection from altering the database.
  - `setupDatabase()`: Creates tables: `EmployeeProfiles`, `EmployeeSkills`, `DesignationHistory`, `ScraperHashes`, `QueryCache`, and `LLMUsageLog`.
  - `ingestEmployeeData(jsonFilePath)`: Parses seed JSON and populates normalized relational tables.
  - `fetchStoredHash(pageUrl)` / `updateStoredHash(pageUrl, newHash)`: Manages delta synchronization hashes.
  - `logLLMUsage(...)`: Records model calls, prompt/response tokens, and calculated cost into `LLMUsageLog`.

#### `core/llmClient.py`
- **Purpose**: Wrapper around Google Gemini LLMs (`gemini-2.5-flash`) and Embedding models (`models/gemini-embedding-001`).
- **How it Works**:
  - `EmbeddingEngineProxy`: Dynamically instantiates `GoogleGenerativeAIEmbeddings` per call to avoid thread/event loop binding issues under Streamlit or background threads.
  - `executeWithRetry(...)`: Resilience layer implementing exponential backoff with random jitter for handling HTTP 429 rate limits or resource exhaustion.
  - `calculateCost(...)`: Tracks token pricing based on model type and prompt length (applying context premium multipliers for large prompts).
  - `invokeFlashLite(prompt)` / `invokeFlash(prompt)`: Asynchronous helper functions that invoke Gemini Flash models with token usage logging.

#### `core/chromaClient.py`
- **Purpose**: Persistent vector database client for ChromaDB storing semantic chunks of the Netsol Technologies website.
- **How it Works**:
  - Initializes `chromadb.PersistentClient` at `data/chromaStorage` with Cosine similarity (`hnsw:space`: `cosine`).
  - `upsertVectorChunks(pageUrl, chunksData)`: Atomically deletes previous chunks matching `source = pageUrl` and inserts new chunks (ids, embeddings, document texts, metadata).
  - `queryVectorDatabase(queryVector, topK=3)`: Performs vector similarity search and returns formatted document text along with source URL headers.

#### `agent/state.py`
- **Purpose**: Defines `ChatbotState`, a `TypedDict` that represents the shared state passed between all nodes in the LangGraph workflow.

#### `agent/tools.py`
- **Purpose**: Security guardrails and helper tools for SQL validation and entity lookup.
- **How it Works**:
  - `validateSqlSyntax(sqlQuery)`: **Security Zone 2** — Uses `sqlglot` to parse the Abstract Syntax Tree (AST) of the generated SQL statement. Ensures the statement is strictly a `SELECT` query and raises a `ValueError` if non-SELECT keywords (DROP, DELETE, UPDATE, INSERT) or invalid syntax are detected.
  - `executeSafeSql(sqlQuery)`: Runs `validateSqlSyntax`, opens a read-only database connection, executes the query, converts rows into list-of-dict records, and safely closes the connection.
  - `getSemanticEntityMatches(userQuery)`: Lightweight synonym dictionary mapper.

#### `agent/nodes.py`
- **Purpose**: Contains all active LangGraph execution nodes.
- **How it Works**: Contains async functions (`routeQueryNode`, `mapEntitiesNode`, `generateSqlNode`, `executeSqlNode`, `retrieveVectorNode`, `synthesizeResponseNode`) that process `ChatbotState` and return state updates.

#### `agent/graph.py`
- **Purpose**: Assembles, wires, and compiles the `StateGraph`.
- **How it Works**: Registers all nodes, sets the entry point (`intentRouter`), attaches conditional edges (`routeAfterIntent`, `routeAfterMapper`, `routeAfterVector`, `routeAfterSql`), defines the terminal edge (`END`), and compiles the graph into `chatbotApp`.

#### `api/routes.py`
- **Purpose**: FastAPI REST API handling chat requests.
- **How it Works**:
  - `POST /api/v1/chat`: Accepts JSON with `userQuery` and `chatHistory`, constructs initial `ChatbotState`, runs `await chatbotApp.ainvoke(initialState)`, and returns `ChatResponse`.
  - `POST /api/v1/chat/file`: Accepts multipart form data (`file`, `userQuery`, `chatHistory`), extracts file text using `extractTextFromFile`, injects it into `fileContext` in `ChatbotState`, and invokes `chatbotApp`.

#### `scraper/playwrightEngine.py`
- **Purpose**: Context manager wrapping Playwright Chromium for web scraping.
- **How it Works**: Launches headless Chromium, navigates to target pages, waits for `networkidle`, scrolls incrementally (800px steps) to lazy-load content, evaluates browser JavaScript to auto-click accordions/tabs/toggles/"Read More" buttons, and returns full HTML and page title.

#### `scraper/crawlerUtils.py`
- **Purpose**: Scraper helper utilities.
- **How it Works**:
  - `shouldProcessUrl(url)`: Validates domain boundaries (`netsoltech.com`, `ir.netsoltech.com`), excludes static assets (`.pdf`, `.jpg`, `.png`, etc.), and filters out blog, news, press-release, and insight article paths.
  - `chunkText(text, pageTitle, chunkSize=1000, overlap=100)`: Splits clean text into overlapping chunks, searching backward for sentence/word boundaries, and prepending page title metadata.

#### `scraper/syncTask.py`
- **Purpose**: Background delta sync task.
- **How it Works**: Crawls seed URLs up to 50 pages, extracts text, computes SHA-256 content hashes, compares them against `ScraperHashes` in SQLite. If unchanged, skips re-embedding. If changed, chunks the text, computes embeddings via Gemini, upserts to ChromaDB, and updates the stored hash.

#### `utils/fileExtractor.py`
- **Purpose**: Document text extraction service supporting `.txt`, `.md`, `.pdf` (via `pypdf`), `.docx` (via `python-docx`), and legacy `.doc` (via binary regex extraction). Enforces a 5MB maximum file size limit.

#### `streamlit_app.py`
- **Purpose**: Alternative Streamlit host application embedding `static/index.html` via a custom component, bridging iframe postMessage communications with the LangGraph state machine.

---

## 2. LangGraph Architecture Deep Dive

### State Schema (`ChatbotState`)

The state dictionary is defined in `agent/state.py` as follows:

```python
class ChatbotState(TypedDict):
    # Core Input
    userQuery: str
    chatHistory: List[Dict[str, str]]
    fileContext: str
    
    # Routing & Mapping
    queryIntent: str  # 'SQL', 'VECTOR', 'HYBRID', 'FILE', 'OUT_OF_DOMAIN'
    extractedEntities: List[str]
    vectorQuery: str
    
    # SQL Execution Pathway
    generatedSql: str
    sqlResult: List[Dict[str, Any]]
    
    # Vector Retrieval Pathway
    retrievedContext: List[str]
    
    # Validation & Output
    errorLog: str
    retryCount: int
    entityCorrections: List[str]
    finalResponse: str
```

#### State Keys Breakdown & Mutations

| Key | Type | Purpose | Mutated By (Node) |
|---|---|---|---|
| `userQuery` | `str` | Raw or contextualized user prompt | Input / `intentRouter` (reformulated query) |
| `chatHistory` | `List[Dict[str, str]]` | Recent conversation messages | Input / REST API |
| `fileContext` | `str` | Extracted text from uploaded document | REST API / Streamlit |
| `queryIntent` | `str` | Intent classification (`SQL`, `VECTOR`, `HYBRID`, `FILE`, `OUT_OF_DOMAIN`) | `intentRouter` |
| `extractedEntities` | `List[str]` | Exact DB department/skill/designation names | `semanticMapper` |
| `vectorQuery` | `str` | Sub-query optimized for vector search | `semanticMapper` |
| `generatedSql` | `str` | Text-to-SQL query string generated by LLM | `sqlGenerator` |
| `sqlResult` | `List[Dict[str, Any]]` | Formatted dictionary rows from SQLite execution | `sqlExecutor` |
| `retrievedContext` | `List[str]` | Relevant vector chunks retrieved from ChromaDB | `vectorRetriever` |
| `errorLog` | `str` | SQL syntax or execution error message | `sqlExecutor` |
| `retryCount` | `int` | Counter tracking SQL self-correction attempts | `sqlExecutor` (incremented on failure) |
| `entityCorrections` | `List[str]` | Polished correction messages for missing DB entities | `semanticMapper` |
| `finalResponse` | `str` | Final synthesized textual answer returned to user | `responseSynthesizer` |

---

### Node Specifications

LangGraph nodes are registered in `agent/graph.py` and implemented in `agent/nodes.py`.

```
                  +-------------------+
                  |   intentRouter    |
                  +---------+---------+
                            |
           +----------------+----------------+
           |                |                |
           v                v                v
  (SQL / HYBRID)         (VECTOR)     (OUT_OF_DOMAIN / FILE)
    +------+------+   +-----+------+   +-----+------+
    |semanticMapper|  |vectorRetriever| | response   |
    +------+------+   +-----+------+   |Synthesizer |
           |                |          +-----+------+
     +-----+-----+          |                ^
     |           |          v                |
(HYBRID)       (SQL)  (Synthesizer)----------+
     |           |                           |
     v           v                           |
+----+----+ +----+----+                      |
| vector  | |   sql   |                      |
|Retriever| |Generator|                      |
+----+----+ +----+----+                      |
     |           |                           |
     v           v                           |
(sqlGen)    +----+----+                      |
            |   sql   |                      |
            | Executor|                      |
            +----+----+                      |
                 |                           |
        +--------+--------+                  |
        |                 |                  |
(Error & Retry<3)   (Success / Max Retry)    |
        |                 |                  |
        v                 +------------------+
  (sqlGenerator)
```

#### 1. Router Node: `intentRouter` (`routeQueryNode`)
- **Type**: Agent / Decision Node (Flash-Lite LLM + Deterministic Python checks).
- **Reads**: `userQuery`, `fileContext`, `chatHistory`.
- **Logic**:
  1. If `fileContext` is present, bypasses routing immediately -> sets `queryIntent = "FILE"`.
  2. Runs deterministic regex checks for standalone greetings ("hi", "hello") and bot identity questions ("who are you", "what can you do"). If matched, routes directly to `queryIntent = "VECTOR"`.
  3. If `chatHistory` exists, uses `invokeFlashLite` to rewrite the user query into a self-contained question resolving pronouns and context.
  4. Prompt-classifies query into `SQL`, `VECTOR`, `HYBRID`, or `OUT_OF_DOMAIN`.
- **Writes**: `{"queryIntent": cleanIntent, "userQuery": contextualizedQuery}`.

#### 2. Entity Mapper Node: `semanticMapper` (`mapEntitiesNode`)
- **Type**: Agent Node (Flash-Lite LLM).
- **Reads**: `userQuery`.
- **Logic**:
  - Compares the query against hardcoded lists of valid database departments, skills, and common designations.
  - Extracts search entities, maps fuzzy synonyms (e.g. "it security" -> "Information Security"), formats entity correction notes if a queried DB entity does not exist, and extracts clean vector sub-queries (`vectorQuery`) for compound/hybrid prompts.
- **Writes**: `{"extractedEntities": [...], "entityCorrections": [...], "vectorQuery": "..."}`.

#### 3. Vector Search Node: `vectorRetriever` (`retrieveVectorNode`)
- **Type**: Tool / Retrieval Node.
- **Reads**: `userQuery`, `vectorQuery`.
- **Logic**:
  - Generates query embedding via `embeddingEngine.embed_query(vectorQuery)`.
  - Queries `chromaClient.queryVectorDatabase(queryVector, topK=3)` to obtain relevant website chunks with source URLs.
- **Writes**: `{"retrievedContext": [...]}`.

#### 4. SQL Generator Node: `sqlGenerator` (`generateSqlNode`)
- **Type**: Agent Node (Flash LLM).
- **Reads**: `userQuery`, `extractedEntities`, `errorLog`.
- **Logic**:
  - Receives strict schema definitions for `EmployeeProfiles`, `EmployeeSkills`, and `DesignationHistory`.
  - Applies prompt rules: strict SELECT queries, max 50 rows, LIKE wildcards for fuzzy name matching, proper table names (`EmployeeProfiles`), aggregate column aliasing, and initial designation progression logic.
  - If `errorLog` is non-empty (retry loop), appends error feedback to prompt for structural self-correction.
  - Passes generated SQL through Python regex replacements to fix table name hallucinations.
- **Writes**: `{"generatedSql": cleanSql}`.

#### 5. SQL Executor Node: `sqlExecutor` (`executeSqlNode`)
- **Type**: Tool / Execution Node (Python DB Hook).
- **Reads**: `generatedSql`.
- **Logic**:
  - Opens SQLite connection to `settings.dbPath`.
  - Executes `generatedSql`, fetches description headers, formats results into `List[Dict[str, Any]]`.
  - On success: Returns results and clears `errorLog`.
  - On failure: Catches SQLite exception, logs error into `errorLog`, and increments retry state implicitly.
- **Writes**: `{"sqlResult": formattedResults, "errorLog": ""}` (on success) or `{"sqlResult": [], "errorLog": str(e)}` (on error).

#### 6. Response Synthesizer Node: `responseSynthesizer` (`synthesizeResponseNode`)
- **Type**: Agent Node (Flash LLM + Deterministic Guards).
- **Reads**: `userQuery`, `queryIntent`, `fileContext`, `sqlResult`, `generatedSql`, `retrievedContext`, `entityCorrections`.
- **Logic**:
  - Intercepts greetings and bot identity questions with static branded replies ("I am NetAssist! 🤖...").
  - If `queryIntent == "OUT_OF_DOMAIN"`: Returns clean domain deflection response.
  - If `queryIntent == "FILE"`: Synthesizes direct answer solely from `fileContext`.
  - For `SQL`, `VECTOR`, and `HYBRID`: Bundles SQL tabular data, vector chunks, and entity correction notes into prompt payload, invoking Gemini Flash to produce a direct, concise markdown response.
- **Writes**: `{"finalResponse": finalAnswer}`.

---

### Conditional Edges & Routing Logic

The conditional edges control execution flow between nodes.

```python
# 1. Edge after intentRouter
workflowGraph.add_conditional_edges(
    "intentRouter",
    routeAfterIntent,
    {
        "semanticMapper": "semanticMapper",
        "vectorRetriever": "vectorRetriever",
        "responseSynthesizer": "responseSynthesizer"
    }
)
```
- **`routeAfterIntent(state)`**:
  - If `queryIntent` in `["SQL", "HYBRID"]` -> `semanticMapper`.
  - If `queryIntent == "VECTOR"` -> `vectorRetriever`.
  - If `queryIntent in ["OUT_OF_DOMAIN", "FILE"]` -> `responseSynthesizer`.

```python
# 2. Edge after semanticMapper
workflowGraph.add_conditional_edges(
    "semanticMapper",
    routeAfterMapper,
    {
        "vectorRetriever": "vectorRetriever",
        "sqlGenerator": "sqlGenerator"
    }
)
```
- **`routeAfterMapper(state)`**:
  - If `queryIntent == "HYBRID"` -> `vectorRetriever` (to fetch vector context before generating SQL).
  - Else (`SQL`) -> `sqlGenerator`.

```python
# 3. Edge after vectorRetriever
workflowGraph.add_conditional_edges(
    "vectorRetriever",
    routeAfterVector,
    {
        "sqlGenerator": "sqlGenerator",
        "responseSynthesizer": "responseSynthesizer"
    }
)
```
- **`routeAfterVector(state)`**:
  - If `queryIntent == "HYBRID"` -> `sqlGenerator` (continues the hybrid pipeline).
  - Else (`VECTOR`) -> `responseSynthesizer`.

```python
# 4. Edge after sqlExecutor (The Self-Correction Loop)
workflowGraph.add_conditional_edges(
    "sqlExecutor",
    routeAfterSql,
    {
        "sqlGenerator": "sqlGenerator",
        "responseSynthesizer": "responseSynthesizer"
    }
)
```
- **`routeAfterSql(state)`**:
  - If `errorLog` is non-empty AND `retryCount < 3` -> routes back to `sqlGenerator` with error context attached.
  - Otherwise (success or retries exhausted) -> `responseSynthesizer`.

---

## 3. Tools Used Across the System

| Tool Function | File Location | Purpose | Invoked By |
|---|---|---|---|
| `validateSqlSyntax(sqlQuery)` | `agent/tools.py` | AST parsing via `sqlglot` to enforce SELECT statements | Security layer before SQL execution |
| `executeSafeSql(sqlQuery)` | `agent/tools.py` | Read-only SQLite query execution wrapper | `agent/tools.py` / database helper |
| `getSemanticEntityMatches(userQuery)` | `agent/tools.py` | Synonym dictionary matching | Entity processing |
| `queryVectorDatabase(queryVector, topK)` | `core/chromaClient.py` | Vector similarity search in ChromaDB | `vectorRetriever` node |
| `upsertVectorChunks(...)` | `core/chromaClient.py` | Vector chunk storage | Background scraper `syncTask.py` |
| `extractTextFromFile(file, content)` | `utils/fileExtractor.py` | Multi-format document parser (.pdf, .docx, .doc, .txt, .md) | `api/routes.py` (`processChatWithFile`) |
| `invokeFlashLite(prompt)` | `core/llmClient.py` | Fast LLM inference with retry resilience | `intentRouter`, `semanticMapper` |
| `invokeFlash(prompt)` | `core/llmClient.py` | High-reasoning LLM inference | `sqlGenerator`, `responseSynthesizer` |

---

## 4. End-to-End User Prompt Pipeline

Here is the complete step-by-step lifecycle of a user prompt moving through the NetAssist system.

### Step 1: User Request Entry
- A user sends a prompt (e.g. *"What is the average salary in Information Security and tell me about Transcend platform?"*) via the embedded web frontend or API.
- The web UI posts a JSON payload to `POST /api/v1/chat`.

### Step 2: State Initialization
- `api/routes.py` catches the HTTP request and constructs the initial `ChatbotState`:
  - `userQuery` = `"What is the average salary in Information Security and tell me about Transcend platform?"`
  - `chatHistory` = `[...previous messages...]`
  - `fileContext` = `""`
  - `retryCount` = `0`
  - All other fields initialized to empty defaults.
- Calls `await chatbotApp.ainvoke(initialState)`.

### Step 3: Intent Routing (`intentRouter`)
- Bypasses file context check (`fileContext` is empty).
- Evaluates conversation history and reformulates query if needed.
- Invokes `invokeFlashLite` to classify the intent:
  - Result: `queryIntent = "HYBRID"` (since it asks for both employee metrics and product information).

### Step 4: Conditional Routing (1)
- `routeAfterIntent` checks `queryIntent` (`HYBRID`) -> Routes to `semanticMapper`.

### Step 5: Entity Mapping (`semanticMapper`)
- Compares user terms against database schema concepts:
  - Maps `"Information Security"` to valid department string `"Information Security"`.
  - Extracts sub-query for vector retrieval: `vectorQuery = "Transcend platform"`.
- Updates state with `extractedEntities = ["Information Security"]` and `vectorQuery = "Transcend platform"`.

### Step 6: Conditional Routing (2)
- `routeAfterMapper` checks `queryIntent` (`HYBRID`) -> Routes to `vectorRetriever`.

### Step 7: Vector Retrieval (`vectorRetriever`)
- Converts `vectorQuery` (`"Transcend platform"`) into vector embeddings using `embeddingEngine.embed_query`.
- Queries ChromaDB collection `netsolWebsite` for top 3 matching text chunks.
- Updates state with `retrievedContext = ["[Source: https://netsoltech.com/solutions/transcend]\nContent: ..."]`.

### Step 8: Conditional Routing (3)
- `routeAfterVector` checks `queryIntent` (`HYBRID`) -> Routes to `sqlGenerator`.

### Step 9: SQL Generation (`sqlGenerator`)
- Passes schema for `EmployeeProfiles`, `EmployeeSkills`, `DesignationHistory` and `extractedEntities = ["Information Security"]` to Gemini Flash.
- LLM generates SQL:
  ```sql
  SELECT AVG(currentSalary) AS AverageSalary 
  FROM EmployeeProfiles 
  WHERE currentDepartment LIKE '%Information Security%';
  ```
- Applies table name guardrails and updates state with `generatedSql`.

### Step 10: SQL Execution (`sqlExecutor`)
- Executes generated SQL against local read-only SQLite database.
- Obtains result: `sqlResult = [{"AverageSalary": 145000}]`.
- Clears `errorLog`.

### Step 11: Conditional Routing (4)
- `routeAfterSql` checks `errorLog` (empty) -> Routes to `responseSynthesizer`.

### Step 12: Response Synthesis (`responseSynthesizer`)
- Bundles all gathered context:
  - SQL Result: `AverageSalary: 145000`
  - Vector Context: Transcend platform details
- Prompts Gemini Flash to synthesize a brief, structured markdown reply.
- Updates state with `finalResponse`.

### Step 13: Terminal Exit & API Response
- LangGraph hits `END` edge and completes execution.
- `api/routes.py` extracts `finalResponse`, `queryIntent`, `retryCount` and returns HTTP 200 JSON to frontend:
  ```json
  {
    "response": "• **Average Salary (Information Security):** $145,000\n• **Transcend Platform:** NETSOL's digital transformation platform designed for asset finance and leasing...",
    "intent": "HYBRID",
    "retryCount": 0
  }
  ```
- Web UI renders the response markdown in the chat window.
