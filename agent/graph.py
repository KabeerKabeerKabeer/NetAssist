from langgraph.graph import StateGraph, END
from agent.state import ChatbotState
from agent.nodes import (
    routeQueryNode,
    mapEntitiesNode,
    retrieveVectorNode,
    generateSqlNode,
    executeSqlNode,
    synthesizeResponseNode
)

# --- Routing Logic Functions ---

def routeAfterIntent(stateData: ChatbotState) -> str:
    """
    Determines the first major pathway based on the classification.
    """
    queryIntent = stateData.get("queryIntent")
    
    if queryIntent in ["SQL", "HYBRID"]:
        return "semanticMapper"
    elif queryIntent == "VECTOR":
        return "vectorRetriever"
    else:
        # OUT_OF_DOMAIN goes straight to synthesis for a safe refusal
        return "responseSynthesizer"

def routeAfterMapper(stateData: ChatbotState) -> str:
    """
    If the query is HYBRID, routes to vector retrieval after entity mapping.
    Otherwise (SQL), routes directly to SQL generation.
    """
    queryIntent = stateData.get("queryIntent")
    if queryIntent == "HYBRID":
        return "vectorRetriever"
    return "sqlGenerator"

def routeAfterVector(stateData: ChatbotState) -> str:
    """
    If the query is HYBRID, routes to SQL generation after vector retrieval.
    Otherwise (VECTOR), goes straight to synthesis.
    """
    queryIntent = stateData.get("queryIntent")
    if queryIntent == "HYBRID":
        return "sqlGenerator"
    return "responseSynthesizer"

def routeAfterSql(stateData: ChatbotState) -> str:
    """
    The Self-Correction Loop. If the AST parser or SQLite throws an error,
    it routes back to the generator up to 3 times before giving up.
    """
    errorLog = stateData.get("errorLog")
    retryCount = stateData.get("retryCount", 0)
    
    if errorLog and retryCount < 3:
        return "sqlGenerator"
    return "responseSynthesizer"

# --- Graph Construction ---

# 1. Initialize the State Machine
workflowGraph = StateGraph(ChatbotState)

# 2. Register all execution nodes
workflowGraph.add_node("intentRouter", routeQueryNode)
workflowGraph.add_node("semanticMapper", mapEntitiesNode)
workflowGraph.add_node("vectorRetriever", retrieveVectorNode)
workflowGraph.add_node("sqlGenerator", generateSqlNode)
workflowGraph.add_node("sqlExecutor", executeSqlNode)
workflowGraph.add_node("responseSynthesizer", synthesizeResponseNode)

# 3. Define Entry Point
workflowGraph.set_entry_point("intentRouter")

# 4. Wire the conditional logic and edges
workflowGraph.add_conditional_edges(
    "intentRouter",
    routeAfterIntent,
    {
        "semanticMapper": "semanticMapper",
        "vectorRetriever": "vectorRetriever",
        "responseSynthesizer": "responseSynthesizer"
    }
)

workflowGraph.add_conditional_edges(
    "semanticMapper",
    routeAfterMapper,
    {
        "vectorRetriever": "vectorRetriever",
        "sqlGenerator": "sqlGenerator"
    }
)

workflowGraph.add_conditional_edges(
    "vectorRetriever",
    routeAfterVector,
    {
        "sqlGenerator": "sqlGenerator",
        "responseSynthesizer": "responseSynthesizer"
    }
)

# Standard sequential edges for the SQL pathway
workflowGraph.add_edge("sqlGenerator", "sqlExecutor")

workflowGraph.add_conditional_edges(
    "sqlExecutor",
    routeAfterSql,
    {
        "sqlGenerator": "sqlGenerator",
        "responseSynthesizer": "responseSynthesizer"
    }
)

# 5. Define the Exit Point
workflowGraph.add_edge("responseSynthesizer", END)

# 6. Compile into an executable application
chatbotApp = workflowGraph.compile()