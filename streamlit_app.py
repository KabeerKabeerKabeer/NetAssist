import streamlit as st
import asyncio
import os
import json
from dotenv import load_dotenv

# Load environmental variables
load_dotenv()

# Import core structures
from agent.graph import chatbotApp
from agent.state import ChatbotState
from utils.fileExtractor import extractTextFromFile

# Mock UploadFile class for FastAPI helper compatibility
class StreamlitFileMock:
    def __init__(self, filename):
        self.filename = filename

# Page configuration
st.set_page_config(
    page_title="NetAssist | Netsol Hybrid RAG",
    page_icon="🤖",
    layout="centered"
)

# Custom Styling (matching our beautiful SOTA dark/light themes)
st.markdown("""
<style>
    /* Styling headers & text */
    h1 {
        font-family: 'Hanken Grotesk', sans-serif !important;
        background: linear-gradient(45deg, #005c98, #1B75BB);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-weight: 800 !important;
    }
    .stChatInputContainer {
        border-radius: 1rem !important;
    }
    div.stChatMessage {
        border-radius: 1rem !important;
        box-shadow: 0 4px 12px rgba(0,0,0,0.02);
    }
</style>
""", unsafe_allow_html=True)

st.title("NetAssist")
st.caption("Netsol Hybrid Intelligence OS — SQL & Vector RAG Pipeline")

# Initialize Chat Sessions
if "messages" not in st.session_state:
    st.session_state.messages = []

# Sidebar for file upload and parameters
with st.sidebar:
    st.header("Attachment Node")
    uploaded_file = st.file_uploader(
        "Upload document (.pdf, .docx, .doc, .txt, .md)", 
        type=["pdf", "docx", "doc", "txt", "md"]
    )
    
    st.divider()
    st.markdown("### System Specifications")
    st.markdown("""
    - **Context Limit:** 8,192 tokens
    - **RAG Architecture:** Hybrid (SQL / ChromaDB Vector)
    - **Backend Engine:** LangGraph State Machine
    """)
    
    # Add a Clear Chat button
    if st.button("Clear Chat History", type="secondary"):
        st.session_state.messages = []
        st.rerun()

# Display chat messages from session state
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if "intent" in msg:
            st.caption(f"Intent detected: **{msg['intent']}**")

# Chat input
if user_query := st.chat_input("Query the neural index..."):
    # Render user query
    with st.chat_message("user"):
        st.markdown(user_query)
    
    # Save user query to history
    st.session_state.messages.append({"role": "user", "content": user_query})
    
    # Extract file text if file attached
    file_text = ""
    if uploaded_file is not None:
        try:
            content_bytes = uploaded_file.getvalue()
            file_mock = StreamlitFileMock(uploaded_file.name)
            file_text = extractTextFromFile(file_mock, content_bytes)
            st.info(f"Attached: **{uploaded_file.name}** ({len(file_text)} characters extracted)")
        except Exception as file_err:
            st.error(f"Failed to parse uploaded file: {str(file_err)}")
            st.stop()
            
    # Structure state payload
    history_payload = []
    # Build history list in required structure: [{"role": "user"|"assistant", "content": "..."}]
    for m in st.session_state.messages[:-1]: # exclude current message
        history_payload.append({
            "role": m["role"],
            "content": m["content"]
        })
        
    initialState = ChatbotState(
        userQuery=user_query,
        chatHistory=history_payload,
        fileContext=file_text,
        queryIntent="",
        extractedEntities=[],
        generatedSql="",
        sqlResult=[],
        retrievedContext=[],
        errorLog="",
        retryCount=0,
        finalResponse=""
    )
    
    # Invoke LangGraph agent with loading indicator
    with st.spinner("Neural agent thinking..."):
        try:
            # Run the async invoker in an event loop
            finalState = asyncio.run(chatbotApp.ainvoke(initialState))
            response = finalState.get("finalResponse", "I am unable to answer that at the moment.")
            intent = finalState.get("queryIntent", "UNKNOWN")
            
            # Display response
            with st.chat_message("assistant"):
                st.markdown(response)
                st.caption(f"Intent detected: **{intent}**")
                
            # Save assistant response to history
            st.session_state.messages.append({
                "role": "assistant", 
                "content": response,
                "intent": intent
            })
            
        except Exception as e:
            st.error(f"Error processing response: {str(e)}")
