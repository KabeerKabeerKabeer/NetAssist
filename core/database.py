import sqlite3
import json
import os
from core.config import settings

def getWriteConnection():
    # Used only by backend ingestion and background scraper
    return sqlite3.connect(settings.dbPath)

def getReadOnlyConnection():
    # Security Zone 3: Used by the LangGraph AST Executor
    absolutePath = os.path.abspath(settings.dbPath)
    uriString = f"file:{absolutePath}?mode=ro"
    return sqlite3.connect(uriString, uri=True)

def setupDatabase():
    dbConnection = getWriteConnection()
    dbCursor = dbConnection.cursor()

    # 1. Core Profile Table
    dbCursor.execute("""
        CREATE TABLE IF NOT EXISTS EmployeeProfiles (
            employeeId TEXT PRIMARY KEY,
            employeeName TEXT,
            gender TEXT,
            currentDepartment TEXT,
            currentDesignation TEXT,
            initialDepartment TEXT,
            initialDesignation TEXT,
            currentSalary INTEGER,
            joiningDate TEXT
        )
    """)

    # 2. Normalized Skills Mapping Table
    dbCursor.execute("""
        CREATE TABLE IF NOT EXISTS EmployeeSkills (
            mappingId INTEGER PRIMARY KEY AUTOINCREMENT,
            employeeId TEXT,
            skillName TEXT,
            FOREIGN KEY(employeeId) REFERENCES EmployeeProfiles(employeeId)
        )
    """)

    # 3. Normalized Designation History Table
    dbCursor.execute("""
        CREATE TABLE IF NOT EXISTS DesignationHistory (
            historyId INTEGER PRIMARY KEY AUTOINCREMENT,
            employeeId TEXT,
            pastDesignation TEXT,
            effectiveDate TEXT,
            FOREIGN KEY(employeeId) REFERENCES EmployeeProfiles(employeeId)
        )
    """)

    # 4. Scraper Delta-Sync Table
    dbCursor.execute("""
        CREATE TABLE IF NOT EXISTS ScraperHashes (
            pageUrl TEXT PRIMARY KEY,
            contentHash TEXT
        )
    """)

    # 5. LLM Response Cache
    dbCursor.execute("""
        CREATE TABLE IF NOT EXISTS QueryCache (
            queryHash TEXT PRIMARY KEY,
            userQuery TEXT,
            generatedSql TEXT,
            finalResponse TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 6. LLM Token Usage Logs
    dbCursor.execute("""
        CREATE TABLE IF NOT EXISTS LLMUsageLog (
            usageId INTEGER PRIMARY KEY AUTOINCREMENT,
            modelName TEXT,
            promptTokens INTEGER,
            responseTokens INTEGER,
            estimatedCost REAL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    dbConnection.commit()
    dbConnection.close()

def ingestEmployeeData(jsonFilePath):
    with open(jsonFilePath, 'r') as fileObj:
        jsonData = json.load(fileObj)

    dbConnection = getWriteConnection()
    dbCursor = dbConnection.cursor()

    for empRecord in jsonData:
        empName = empRecord.get('employee_name')
        empId = empRecord.get('employee_id')

        # Drop garbage rows immediately
        if not empName or "Sheet" in str(empId):
            continue

        # Insert Core Data
        dbCursor.execute("""
            INSERT OR IGNORE INTO EmployeeProfiles 
            (employeeId, employeeName, gender, currentDepartment, currentDesignation, initialDepartment, initialDesignation, currentSalary, joiningDate)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            empId, 
            empName, 
            empRecord.get('gender'), 
            empRecord.get('current_department'), 
            empRecord.get('current_designation'), 
            empRecord.get('initial_department'),
            empRecord.get('initial_designation'),
            empRecord.get('salary_amount', 0), 
            empRecord.get('joining_date')
        ))

        # Insert Skills / Tools (Flattening the array)
        techList = empRecord.get('tools_or_technologies', [])
        for techItem in techList:
            dbCursor.execute("""
                INSERT INTO EmployeeSkills (employeeId, skillName)
                VALUES (?, ?)
            """, (empId, techItem))
            
        # Insert History (Flattening the array)
        historyList = empRecord.get('designation_history', [])
        for historyItem in historyList:
            dbCursor.execute("""
                INSERT INTO DesignationHistory (employeeId, pastDesignation, effectiveDate)
                VALUES (?, ?, ?)
            """, (empId, historyItem.get('designation'), historyItem.get('effective_date')))

    dbConnection.commit()
    dbConnection.close()
    print("Employee JSON data successfully ingested into normalized SQLite tables.")

# --- Scraper Helper Functions ---

def fetchStoredHash(pageUrl):
    dbConnection = getReadOnlyConnection()
    dbCursor = dbConnection.cursor()
    dbCursor.execute("SELECT contentHash FROM ScraperHashes WHERE pageUrl = ?", (pageUrl,))
    resultRow = dbCursor.fetchone()
    dbConnection.close()
    
    if resultRow:
        return resultRow[0]
    return None

def updateStoredHash(pageUrl, newHash):
    dbConnection = getWriteConnection()
    dbCursor = dbConnection.cursor()
    dbCursor.execute("""
        INSERT OR REPLACE INTO ScraperHashes (pageUrl, contentHash)
        VALUES (?, ?)
    """, (pageUrl, newHash))
    dbConnection.commit()
    dbConnection.close()

def logLLMUsage(modelName: str, promptTokens: int, responseTokens: int, estimatedCost: float):
    """
    Inserts a record of LLM token usage and estimated cost into the LLMUsageLog table.
    Swallows exceptions to ensure main application logic is never blocked or crashed.
    """
    try:
        dbConnection = getWriteConnection()
        dbCursor = dbConnection.cursor()
        dbCursor.execute("""
            INSERT INTO LLMUsageLog (modelName, promptTokens, responseTokens, estimatedCost)
            VALUES (?, ?, ?, ?)
        """, (modelName, promptTokens, responseTokens, estimatedCost))
        dbConnection.commit()
        dbConnection.close()
    except Exception as err:
        print(f"[LLM Usage Logger Error] Failed to log usage details: {err}")