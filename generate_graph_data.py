import os
import json

mermaid_graph = """graph TD
    %% Nodes
    __start__([Start])
    intentRouter[Intent Router<br/><i>Classifies Query & Sets Intent</i>]
    semanticMapper[Semantic Mapper<br/><i>Maps Entities to SQLite Schema</i>]
    vectorRetriever[Vector Retriever<br/><i>Searches ChromaDB Context Chunks</i>]
    sqlGenerator[SQL Generator<br/><i>Generates SQLite Statement</i>]
    sqlExecutor[SQL Executor<br/><i>Runs Query & Validates Schema</i>]
    responseSynthesizer[Response Synthesizer<br/><i>Synthesizes LLM Text Answer</i>]
    __end__([End])

    %% Edges & Conditional Routing
    __start__ --> intentRouter
    
    intentRouter -->|Intent: SQL / HYBRID| semanticMapper
    intentRouter -->|Intent: VECTOR| vectorRetriever
    intentRouter -->|Intent: OUT_OF_DOMAIN| responseSynthesizer
    
    semanticMapper -->|Intent: HYBRID| vectorRetriever
    semanticMapper -->|Intent: SQL| sqlGenerator
    
    vectorRetriever -->|Intent: HYBRID| sqlGenerator
    vectorRetriever -->|Intent: VECTOR| responseSynthesizer
    
    sqlGenerator --> sqlExecutor
    
    sqlExecutor -->|Execution Error / Self-Correction Loop| sqlGenerator
    sqlExecutor -->|Query Execution Success| responseSynthesizer
    
    responseSynthesizer --> __end__

    %% Styling Theme Override
    classDef startEnd fill:#111827,stroke:#3b82f6,stroke-width:2px,color:#fff,rx:15px,ry:15px;
    classDef router fill:#1e1b4b,stroke:#818cf8,stroke-width:2px,color:#fff,rx:8px,ry:8px;
    classDef mapper fill:#5c3e09,stroke:#d97706,stroke-width:2px,color:#fff,rx:8px,ry:8px;
    classDef sql fill:#064e3b,stroke:#059669,stroke-width:2px,color:#fff,rx:8px,ry:8px;
    classDef vector fill:#164e63,stroke:#0891b2,stroke-width:2px,color:#fff,rx:8px,ry:8px;
    classDef synth fill:#581c87,stroke:#9333ea,stroke-width:2px,color:#fff,rx:8px,ry:8px;

    class __start__,__end__ startEnd;
    class intentRouter router;
    class semanticMapper mapper;
    class sqlGenerator,sqlExecutor sql;
    class vectorRetriever vector;
    class responseSynthesizer synth;
"""

try:
    # Save to static directory as JSON
    output_dir = "static"
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "pipeline_graph.json")
    
    with open(output_path, "w") as f:
        json.dump({"mermaid": mermaid_graph}, f, indent=4)
        
    print(f"Successfully generated and saved Mermaid graph to {output_path}")
except Exception as e:
    print(f"Error saving graph: {e}")
