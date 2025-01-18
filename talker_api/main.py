from fastapi import FastAPI, HTTPException
import os
from pydantic import BaseModel
from services.memory_tool import SharedMemoryManagerTool
from services.custom_tools import request_solving_task
from services.conversation_functions import talker_completion_request, store_belief_and_conversation, parse_reasoner_to_string
from langchain_openai import ChatOpenAI
import logging
from fastapi.responses import StreamingResponse
import json
# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

app = FastAPI(title="Talker API")

# Configuration
MONGO_URL = os.environ["MONGO_URL"]
LLM_URL = os.environ["LLM_URL"]
LLM_TOKEN = os.environ["LLM_URL"]

# Initialize shared memory tool
memory_tool = SharedMemoryManagerTool(mongo_uri=MONGO_URL)

# Initialize LLM
llm = ChatOpenAI(
    model="chat_model",
    openai_api_key=LLM_TOKEN,
    openai_api_base=LLM_URL,
    temperature=0.8,
    max_tokens=1024,
    stop=['<|im_end|>', '</s>'],
    extra_body={"min_p": 0.05, "repetition_penalty": 1.05}
)

tools = [request_solving_task]
tools_dict = {"request_solving_task": request_solving_task}
        
class GenerateResponseRequest(BaseModel):
    session_id: str
    user_query: str
    
class InitializeSessionRequest(BaseModel):
    session_id: str
    system_content: str

# API Endpoints
@app.post("/generate_response",
    summary="Generate Talker Response",
    description="Generates a response for a given session and user query. The response is streamed token by token.",
    response_class=StreamingResponse,
    responses={
        200: {"description": "Streamed response containing tokens and events."},
        500: {"description": "Error occurred during generation."},
    }
)
async def generate_response(request: GenerateResponseRequest):
    """
    Generate a response for a given session and user query.

    Args:
        session_id (str): The unique identifier for the session.
        user_query (str): The query from the user.

    Returns:
        StreamingResponse: Tokenized response streamed to the client.
    """
    session_id = request.session_id
    user_query = request.user_query
    logging.info(f"Received request: session_id={session_id}, user_query={user_query}")
    try:
        # Fetch previous beliefs and conversation history
        conversation_history = memory_tool.get_full_conversation(session_id=session_id)
        previous_beliefs = memory_tool.read_belief_state(session_id=session_id, num_to_retrieve=3)
        reasoner_belief = parse_reasoner_to_string(previous_beliefs)
        reasoner_status = previous_beliefs['reasoner'][-1]['status']

        # Update the first system message with the current belief state
        conversation_history[0]['content'] += f"\n\## Current_Belief_state:\n{reasoner_belief}"
        conversation_history.append({
            'role': 'user',
            'content': user_query
        })

        # Tools
        llm_with_tools = llm.bind_tools(tools)

        # Generator function for streaming
        async def response_stream():
            final_result = None
            async for chunk in talker_completion_request(
                llm_with_tools, conversation_history, tools_dict, reasoner_status
            ): 
                if chunk.startswith("event:final_result"):
                    final_result = json.loads(chunk.split("\ndata: ")[1])
                    yield "event:generation_end\ndata: {}\n\n"
                else:
                    yield chunk  # Stream tokens to the client
                
            if final_result:
                updated_history = final_result["history"]
                response_list = final_result["response_list"]

                # Validate response list structure
                if len(response_list) not in [1, 3]:
                    raise HTTPException(status_code=500, detail="Invalid response structure for debugging.")

                # Store belief state and conversation in shared memory
                store_belief_and_conversation(
                    llm, memory_tool, session_id, user_query, previous_beliefs, updated_history, response_list
                )

        return StreamingResponse(response_stream(), media_type="text/event-stream")


    except Exception as e:
        logging.error(f"Error in generate_response: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    
@app.post(
    "/initialize_session",
    summary="Initialize Session",
    description="Initializes a session with the given session ID and system content. This prepares the shared memory for the session.",
    responses={
        200: {"description": "Session initialized successfully."},
        500: {"description": "An error occurred during session initialization."},
    },
)
async def initialize_session(request: InitializeSessionRequest):
    """
    Initialize a session with a session ID and system content.

    Args:
        request (InitializeSessionRequest): The session initialization data.

    Returns:
        dict: A message indicating the result of the initialization.
    """
    try:
        result = memory_tool.initialize(session_id=request.session_id, system_content=request.system_content)
        return {"message": f"Session {request.session_id} initialized successfully. Result: {result}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to initialize session: {str(e)}")