import json
import sqlite3
from typing import Dict, Any, List
from core.llmClient import invokeFlash, invokeFlashLite
from core.config import settings
from agent.state import ChatbotState

# =====================================================================
# 1. THE ROUTER NODE (Flash-Lite for Speed/Cost)
# =====================================================================
async def routeQueryNode(stateData: ChatbotState) -> Dict[str, Any]:
    """
    Acts as the semantic router to decide if the query requires the SQL DB, 
    the ChromaDB vector store, both, or if it violates the domain constraints.
    Refers to chat history to contextualize/reformulate queries if needed.
    """
    userQuery = stateData.get("userQuery")
    fileContext = stateData.get("fileContext", "")
    
    if fileContext:
        print("[ROUTER] File context detected. Bypassing database routing.")
        return {"queryIntent": "FILE", "userQuery": userQuery}
        
    # Check for simple greetings or chatbot meta-questions directly in Python for deterministic speed & accuracy
    clean_query = userQuery.lower().strip().replace("?", "").replace("!", "")
    meta_keywords = ["who are you", "what can you do", "what do you do", "your name", "introduce yourself", "how can you help", "hi", "hello", "hey"]
    if any(k in clean_query for k in meta_keywords):
        print("[ROUTER] Python-matched greeting/meta-query. Routing directly to VECTOR.")
        return {"queryIntent": "VECTOR", "userQuery": userQuery}
        
    chatHistory = stateData.get("chatHistory", [])
    
    contextualizedQuery = userQuery
    if chatHistory:
        reformulatePrompt = f"""
        Given the following conversation history and a follow-up query, rewrite the follow-up query to be a self-contained, clear query that incorporates the context of the history (resolving pronouns, implicit references, etc.).
        Do NOT answer the query, just rewrite it. If no history context is needed for the query, output the original query exactly.
        
        Conversation History:
        {json.dumps(chatHistory, indent=2)}
        
        Follow-up Query: "{userQuery}"
        
        Self-contained Query:
        """
        rawReformulated = await invokeFlashLite(reformulatePrompt)
        contextualizedQuery = rawReformulated.strip().strip('"').strip()
        print(f"[REFORMULATOR] Contextualized Query: '{contextualizedQuery}' (Original: '{userQuery}')")
        userQuery = contextualizedQuery
        
    routePrompt = f"""
    Analyze the user's query and decide the data source needed.
    Query: "{userQuery}"
    
    Data Categories:
    - SQL: Employee data, salaries, roles, departments, technical skills.
    - VECTOR: Netsol enterprise services, platforms (e.g. Transcend), website info, OR questions asking about your own identity (e.g., "who are you?", "what can you do?", "introduce yourself", "how can you help me").
    - HYBRID: Requires cross-referencing employee profiles WITH company product/service info.
    - OUT_OF_DOMAIN: Anything completely unrelated to Netsol Technologies, its employees, or your own helper capabilities.
    
    Respond with ONLY ONE WORD from this exact list: SQL, VECTOR, HYBRID, or OUT_OF_DOMAIN.
    """
    
    rawIntent = await invokeFlashLite(routePrompt)
    cleanIntent = rawIntent.strip().upper()
    
    validIntents = ["SQL", "VECTOR", "HYBRID", "OUT_OF_DOMAIN"]
    if cleanIntent not in validIntents:
        cleanIntent = "OUT_OF_DOMAIN"  # Safety fallback
        
    print(f"[ROUTER] Determined Intent: {cleanIntent}")
    return {"queryIntent": cleanIntent, "userQuery": userQuery}

# =====================================================================
# 1.5. THE ENTITY MAPPING NODE (Flash-Lite)
# =====================================================================
async def mapEntitiesNode(stateData: ChatbotState) -> Dict[str, Any]:
    """
    Extracts, validates, and maps search entities (names, departments, designations, skills)
    against the actual schema values in the SQLite database to correct synonyms and typos.
    """
    userQuery = stateData.get("userQuery")
    
    # Valid DB values
    valid_departments = [
        'WEOM', 'Information Security', 'Transcend', 'Professional Services', 
        'Finance & Accounts', 'NIAI', 'NETSOL Saudi', 'BD', 'Admin Support - Security', 
        'HospitALL', 'Executives Residence', 'Company Secretariat', 'Scientific Computing', 
        'Nspire', 'NETSOL UK', 'Business & Legal Cell', 'NETSOL Australia', 
        'NETSOL Dubai Office', 'Innovation Group', 'NETSOL Financial Suite', 
        'Human Capital Division', 'Services, Planning, & Facilitations', 
        'Global Marketing', 'Procurement & Employee Services', 'otoz', 
        'Business Improvement Group', 'Network Operations & Services', 'Nfs Blue Star', 
        'Netsol Financial Suite Department', 'Netsol Financial Suite Team', 'It', 
        'Network Operations & Services Department', 'Information Security Department', 
        'Transcend Department'
    ]
    
    valid_skills = [
        'Confluence', 'Postman', 'Figma', 'Outlook', 'Jira', 'GitHub', 'Slack', 
        'VS Code', 'IntelliJ', 'MS Teams', 'ICEfaces (JSF)', 'JasperReports', 
        'JasperServer', 'MySQL', 'Oracle', 'PL/SQL'
    ]
    
    common_designations = [
        'Scrum Master', 'Security Engineer', 'Associate Software Engineer', 'Senior QA Engineer', 
        'Accountant', 'QA Engineer', 'Solution Architect', 'DevOps Engineer', 
        'Business Development Executive', 'Backend Engineer', 'Admin Associate', 'Junior Developer', 
        'Product Manager', 'Residence Manager', 'Deputy Company Secretary', 'UX Designer', 
        'AI Engineer', 'Tech Lead', 'Junior Accountant', 'Sales Engineer', 'Finance Associate', 
        'Senior UX Designer', 'Financial Analyst', 'VP Engineering', 'Compliance Officer', 
        'Engineering Manager', 'Trainee QA Engineer', 'AP-AR Manager', 'Head of Department', 
        'Junior Recruiter', 'SOC Analyst', 'Facilities Engineer', 'Software Engineer', 
        'Marketing Associate', 'Junior UI Designer', 'Senior Buyer', 'ML Research Lead', 
        'VP Marketing', 'Technical Manager', 'Senior Software Engineer'
    ]

    prompt = f"""
    You are a semantic query mapper for the NETSOL database. Match the concepts in the user query to the actual database schema values.
    
    User Query: "{userQuery}"
    
    Valid Departments in DB:
    {valid_departments}
    
    Valid Skills in DB:
    {valid_skills}
    
    Common Designations (Roles) in DB:
    {common_designations}
    
    TASK:
    1. Extract search terms (departments, designations/roles, skills, and people names).
    2. Check if they correspond to valid database values.
    3. If they are synonyms or closely related (e.g. "internet security" -> "Information Security", "information security department" -> "Information Security" or "Information Security Department", "pay" -> "Salary"), map them to the correct value(s).
    4. If the user asks for a database entity (department, designation/role, or skill) that does NOT exist in the database but has a close alternative (e.g. "internet security" which does not exist, but "Information Security" does), formulate a polite correction note. DO NOT generate corrections for general company queries, website questions, founders, services, or products, as those are handled by the Vector database.
       Correction format: "There is no [User Term] department/role/skill in NETSOL, although there is a [DB Term] department/role/skill which has..."
    5. QUERY DECONSTRUCTION: If this query asks about company website/founders/services (e.g. "who is the founder of Netsol...") AND database metrics (e.g. "what is the average pay..."), extract a clean sub-query that focuses ONLY on the company website/founder/services part. This will be used to query the vector database without search dilution. If it is not a compound/hybrid query, set "vectorQuery" to the original query.
    
    Respond ONLY with a JSON object containing these keys:
    - "mappedDepartments": list of exact matching department strings from Valid Departments list.
    - "mappedDesignations": list of exact matching designation strings from the database.
    - "mappedSkills": list of exact matching skill strings from Valid Skills list.
    - "extractedNames": list of names of people.
    - "entityCorrections": list of correction strings (if any, otherwise empty list).
    - "vectorQuery": string representing the vector sub-query (e.g., "founder of Netsol").
    
    Do NOT output markdown. Output ONLY valid JSON.
    """
    
    rawResponse = await invokeFlashLite(prompt)
    rawResponse = rawResponse.strip().strip("```json").strip("```").strip()
    
    mapped_entities = []
    corrections = []
    vector_query = userQuery
    
    try:
        data = json.loads(rawResponse)
        mapped_entities.extend(data.get("mappedDepartments", []))
        mapped_entities.extend(data.get("mappedDesignations", []))
        mapped_entities.extend(data.get("mappedSkills", []))
        mapped_entities.extend(data.get("extractedNames", []))
        corrections = data.get("entityCorrections", [])
        vector_query = data.get("vectorQuery", userQuery)
    except Exception as e:
        print(f"[Warning] Failed to parse entity mapper JSON: {e}")
        mapped_entities = [e.strip() for e in rawResponse.split(",") if e.strip()]
        
    print(f"[ENTITY MAPPER] Final Mapped Entities: {mapped_entities}")
    print(f"[ENTITY MAPPER] Corrections: {corrections}")
    print(f"[ENTITY MAPPER] Vector Query: {vector_query}")
    
    return {"extractedEntities": mapped_entities, "entityCorrections": corrections, "vectorQuery": vector_query}

# =====================================================================
# 2. THE SQL GENERATION NODE (Flash - Upgraded Text-to-SQL)
# =====================================================================
async def generateSqlNode(stateData: ChatbotState) -> Dict[str, Any]:
    """
    Uses Gemini Flash to write strict, read-only SQL based on the active schema.
    Applies conditional logic to prevent aggregation breakage while preserving context.
    """
    userQuery = stateData.get("userQuery")
    extractedEntities = stateData.get("extractedEntities", [])
    errorLog = stateData.get("errorLog", "")
    
    dbSchema = """
    Table: EmployeeProfiles  -- Note: ALWAYS use this exact plural name. Do NOT use singular 'EmployeeProfile'.
    Columns:
    - employeeId (TEXT)
    - employeeName (TEXT)
    - gender (TEXT)
    - currentDepartment (TEXT)
    - currentDesignation (TEXT)  -- Note: Use this when the user asks for "role", "title", or "position"
    - initialDepartment (TEXT)
    - initialDesignation (TEXT)  -- Note: Use this when the user asks for "start out as", "starting designation", or "first role"
    - currentSalary (INTEGER)    -- Note: Use this when the user asks for "salary", "pay", or "compensation"
    - joiningDate (TEXT)

    Table: EmployeeSkills
    Columns:
    - mappingId (INTEGER)
    - employeeId (TEXT)          -- Note: Foreign key linking to EmployeeProfiles
    - skillName (TEXT)           -- Note: Use this to match tools, technologies, and abilities

    Table: DesignationHistory
    Columns:
    - historyId (INTEGER)
    - employeeId (TEXT)          -- Note: Foreign key linking to EmployeeProfiles
    - pastDesignation (TEXT)     -- Note: Use this to track previous roles or promotions
    - effectiveDate (TEXT)
    """
    
    sqlPrompt = f"""
    You are an expert SQLite generator. Write a SQL query to answer this request: "{userQuery}"
    
    Database Schema:
    {dbSchema}
    
    Known Exact Entities in the database related to this query: {extractedEntities}
    
    CRITICAL RULES:
    1. Output ONLY the raw SQL string. No markdown formatting, no explanations, no wrapping in ```sql blocks.
    2. ONLY use SELECT statements. 
    3. Always limit results to a maximum of 50 rows.
    4. AMBIGUITY HANDLING: If the query could refer to multiple people (like having two employees with the same name), return the details for ALL matching records. Do not filter down to a single row unless specified.
    5. FUZZY MATCHING: If searching for a person's name or textual property, always use the LIKE operator with wildcards (e.g., WHERE employeeName LIKE '%Name%').
    6. CONTEXTUAL IDENTIFICATION: If querying for attributes of specific employees, always include 'employeeName' in the SELECT clause. However, if the user asks for AGGREGATES (averages, maximums, counts) or general role statistics, do NOT select individual names. Instead, use explicit column aliases (e.g., AVG(currentSalary) AS AverageSalary).
    7. HYBRID / COMPOUND QUERY RULE: If this is a hybrid query asking about company info/founders/products (handled by Vector RAG) AND employee metrics (e.g., average pay), ignore the company/founder/product parts entirely in this SQL query. Write SQL ONLY to query the employee metrics.
    8. CAREER PROGRESSION RULE: If the user asks what roles they can expect if they "start out as" a certain role, search for employees where `initialDesignation` matches that role, and select their `currentDesignation` or `pastDesignation` from the history.
       Example: SELECT DISTINCT currentDesignation FROM EmployeeProfiles WHERE initialDesignation LIKE '%DevOps Engineer%'
    9. GLOBAL COMPANY SCOPE (NETSOL): The entire employee database represents employees of NETSOL. If the user asks for 'employees at NETSOL', 'total number of employees', 'average salary of the company', or similar global metrics, do NOT filter by currentDepartment or currentDesignation (e.g., do NOT write WHERE currentDepartment = 'NETSOL'). Instead, run the aggregate query globally across the entire table (e.g., SELECT COUNT(*) FROM EmployeeProfiles).
    10. STRICT TABLE NAMES: You must use the exact plural table names defined in the schema. Specifically, the profiles table is 'EmployeeProfiles' (plural). Do NOT use singular names like 'EmployeeProfile'.
    """
    
    if errorLog:
        sqlPrompt += f"\n\nWARNING: Your previous query failed with this error: {errorLog}. Fix the structural/syntax issue and try again."
        
    rawSql = await invokeFlash(sqlPrompt)
    cleanSql = rawSql.strip("```sql").strip("```").strip()
    
    # Python-level table name correction guardrail to prevent singular/plural hallucinations
    replacements = {
        "EmployeeProfile": "EmployeeProfiles",
        "EmployeeSkill": "EmployeeSkills",
        "DesignationHistories": "DesignationHistory",
        "DesignationHistorys": "DesignationHistory"
    }
    for old_val, new_val in replacements.items():
        if old_val in cleanSql and new_val not in cleanSql:
            cleanSql = cleanSql.replace(old_val, new_val)
            
    print(f"\n\n!!! RAW LLM SQL OUTPUT !!!\n{cleanSql}\n!!!!!!!!!!!!!!!!!!!!!!!!!!\n\n")
    return {"generatedSql": cleanSql}

# =====================================================================
# 3. THE SQL EXECUTION NODE (Python DB Hook)
# =====================================================================
def executeSqlNode(stateData: ChatbotState) -> Dict[str, Any]:
    """
    Executes the LLM-generated SQL against the local SQLite database.
    Catches errors safely to trigger retry loops if needed.
    """
    generatedSql = stateData.get("generatedSql", "")
    
    if not generatedSql:
        return {"sqlResult": [], "errorLog": "No SQL was generated."}
        
    try:
        conn = sqlite3.connect(settings.dbPath)
        cursor = conn.cursor()
        cursor.execute(generatedSql)
        results = cursor.fetchall()
        
        columnNames = [description[0] for description in cursor.description]
        formattedResults = [dict(zip(columnNames, row)) for row in results]
        
        conn.close()
        
        print(f"[DEBUG SQL SUCCESS] Returned {len(formattedResults)} rows.")
        return {"sqlResult": formattedResults, "errorLog": ""}
        
    except Exception as e:
        print(f"[DEBUG SQL ERROR] Execution Failed: {str(e)}")
        return {"sqlResult": [], "errorLog": str(e)}

# =====================================================================
# 4. THE VECTOR SEARCH NODE (ChromaDB Integration)
# =====================================================================
async def retrieveVectorNode(stateData: ChatbotState) -> Dict[str, Any]:
    """
    Searches ChromaDB for relevant website data chunks based on the prompt.
    """
    from core.chromaClient import queryVectorDatabase
    from core.llmClient import embeddingEngine
    
    userQuery = stateData.get("userQuery")
    vectorQuery = stateData.get("vectorQuery") or userQuery
    
    queryVector = embeddingEngine.embed_query(vectorQuery)
    topMatches = queryVectorDatabase(queryVector=queryVector, topK=3)
    
    # Store as List[str] to match state.py definition; synthesis node joins them
    return {"retrievedContext": topMatches}

# =====================================================================
# 5. THE FINAL SYNTHESIS NODE (Flash)
# =====================================================================
async def synthesizeResponseNode(stateData: ChatbotState) -> Dict[str, Any]:
    """
    Synthesizes data payloads collected across active relational grids 
    or semantic vector chunks into clean, digestible chatbot text replies.
    Handles OUT_OF_DOMAIN safety deflections cleanly.
    """
    userQuery = stateData.get("userQuery")
    queryIntent = stateData.get("queryIntent")
    
    # 1. Catch assistant identity, capability, and greeting queries for custom answers
    clean_query = userQuery.lower().strip().replace("?", "").replace("!", "")
    if any(q in clean_query for q in ["who are you", "your name", "introduce yourself"]):
        return {"finalResponse": "I am **NetAssist**! 🤖 Created specifically to help you with all your NETSOL Technologies questions, database queries, and document analysis."}
    
    if any(q in clean_query for q in ["what can you do", "what do you do", "how can you help", "your capabilities"]):
        return {
            "finalResponse": (
                "I can answer all your NETSOL queries! Here is how I can help:\n\n"
                "*   **Query Employee Profiles (SQL):** Search for designations, joining dates, salaries, or skills (e.g., *'Find who has the highest tenure in the tech division'*).\n"
                "*   **Explore Corporate Data (Vector):** Learn about NETSOL's platforms like Transcend, retail products, or company services.\n"
                "*   **Document Analysis (File RAG):** Upload files (.pdf, .docx, .doc, .txt, .md) to search and analyze their contents instantly."
            )
        }
        
    if any(q in clean_query for q in ["hi", "hello", "hey"]):
        return {"finalResponse": "Hello! I am **NetAssist**! 🤖 How can I help you today?"}
    
    if queryIntent == "OUT_OF_DOMAIN":
        return {"finalResponse": "I apologize, but I am specifically designed to assist with Netsol Technologies' enterprise services and internal employee data. I cannot answer queries outside of this domain."}

    if queryIntent == "FILE":
        fileContext = stateData.get("fileContext", "")
        synthesisPrompt = f"""
        You are a helpful assistant. Construct a direct response to the user's query utilizing ONLY the provided file context.
        Do NOT refer to any external databases or company records.
        If the answer cannot be found or inferred from the file content, state that the information is not available in the uploaded document.
        
        User Query: {userQuery}
        
        Uploaded File Content:
        ---
        {fileContext}
        ---
        
        CRITICAL FORMATTING RULES:
        1. Be direct, crisp, and brief.
        2. Summarize core points using bullet points where possible.
        """
        finalAnswer = await invokeFlash(synthesisPrompt)
        return {"finalResponse": finalAnswer}

    sqlResult = stateData.get("sqlResult", [])
    generatedSql = stateData.get("generatedSql", "")
    retrievedChunks = stateData.get("retrievedContext", [])
    retrievedContext = "\n\n---\n\n".join(retrievedChunks)  # Join list into readable string
    
    contextPayload = ""
    if queryIntent in ["SQL", "HYBRID"]:
        contextPayload += f"SQL Database Results:\n{json.dumps(sqlResult)}\n\n"
    if queryIntent in ["VECTOR", "HYBRID"]:
        contextPayload += f"Website/Vector Data Results:\n{retrievedContext}\n\n"
        
    entityCorrections = stateData.get("entityCorrections", [])
    correctionsContext = ""
    if entityCorrections:
        correctionsContext = "Database Corrections & Mapping Notes:\n" + "\n".join([f"- {c}" for c in entityCorrections])
        
    synthesisPrompt = f"""
    You are a concise enterprise chatbot assistant for NETSOL Technologies. 
    Construct a direct response to the user's query utilizing the provided internal context.
    
    User Query: {userQuery}
    
    Database Corrections (if any):
    {correctionsContext}
    
    Retrieved Context:
    {contextPayload}
    
    CRITICAL FORMATTING RULES:
    1. Be exceptionally direct, crisp, and brief. Do not use filler introductory phrases (e.g., "Based on the data...", "According to the database...").
    2. Summarize core points or structural breakdowns using bullet points where possible.
    3. Limit the entire output block to a maximum of 3-4 sentences or a small bulleted list.
    4. If database/SQL results are empty or the query context cannot be resolved, explicitly state that the profile or information cannot be found in company records.
    5. If Database Corrections are present, make sure to integrate them directly into your response. For example, if there is a correction saying "There is no internet security department in NETSOL although there is a information security department...", you should output that sentence and append the average pay from the SQL result.
    """
    
    finalAnswer = await invokeFlash(synthesisPrompt)
    return {"finalResponse": finalAnswer}