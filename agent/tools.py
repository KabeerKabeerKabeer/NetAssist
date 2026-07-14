import sqlglot
from core.database import getReadOnlyConnection

def validateSqlSyntax(sqlQuery):
    """
    Zone 2 Security: Parses the AST of the generated SQL.
    Returns True if safe (SELECT only), raises an Exception if malicious.
    """
    if not sqlQuery or sqlQuery.isspace():
        raise ValueError("Generated SQL is empty.")
        
    try:
        # Parse the query into an AST
        parsedStatements = sqlglot.parse(sqlQuery, read="sqlite")
        
        for statement in parsedStatements:
            if not statement:
                continue
                
            # Check if the root node is a SELECT statement
            if not isinstance(statement, sqlglot.exp.Select):
                raise ValueError(f"CRITICAL: Non-SELECT statement detected -> {statement.sql()}")
                
        return True
        
    except sqlglot.errors.ParseError as parseErr:
        raise ValueError(f"SQL Syntax Error: {parseErr}")

def executeSafeSql(sqlQuery):
    """
    Executes the validated SQL query against the read-only database.
    """
    validateSqlSyntax(sqlQuery)
    
    dbConnection = getReadOnlyConnection()
    dbCursor = dbConnection.cursor()
    
    try:
        dbCursor.execute(sqlQuery)
        columnHeaders = [desc[0] for desc in dbCursor.description]
        fetchedRows = dbCursor.fetchall()
        
        # Convert tuples to list of dictionaries for the LLM
        formattedResults = []
        for row in fetchedRows:
            formattedResults.append(dict(zip(columnHeaders, row)))
            
        return formattedResults
        
    except Exception as dbError:
        raise ValueError(f"Database Execution Error: {dbError}")
        
    finally:
        dbConnection.close()

def getSemanticEntityMatches(userQuery):
    """
    A lightweight dictionary check to map user terms (like 'IT Security')
    to exact database values (like 'Information Security') without wasting tokens.
    """
    userQueryLower = userQuery.lower()
    matchedEntities = []
    
    # This dictionary would ideally be populated dynamically at startup, 
    # but here is the structural implementation for the exact matches.
    synonymMap = {
        "it security": "Information Security",
        "cyber security": "Information Security",
        "dev ops": "DevOps",
        "hr": "Human Resources",
        "leads": "Team Lead",
        "heads": "Department Head"
    }
    
    for synonym, exactMatch in synonymMap.items():
        if synonym in userQueryLower and exactMatch not in matchedEntities:
            matchedEntities.append(exactMatch)
            
    return matchedEntities