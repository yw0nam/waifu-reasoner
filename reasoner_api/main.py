from fastapi import FastAPI, HTTPException
import ast, os, logging
from pydantic import BaseModel
from services.memory_tool import SharedMemoryManagerTool
from services.prompt import DEFAULT_REASONER_PROMPT
from services.utils import OpenAIEngine, load_agents
# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

app = FastAPI(title="Reasoner API")

# Configuration
MONGO_URL = os.environ["MONGO_URL"]
LLM_URL = os.environ["LLM_URL"]
LLM_API_KEY = os.environ["LLM_API_KEY"] 

# Initialize shared memory tool
memory_tool = SharedMemoryManagerTool(mongo_uri=MONGO_URL)
openai_engine = OpenAIEngine(url=LLM_URL, token=LLM_API_KEY, temperature=0.9) 

reasoner = load_agents(openai_engine, DEFAULT_REASONER_PROMPT)
        
class ReasoningRequest(BaseModel):
    session_id: str

@app.post("/start_reasoning",
    summary="Start reasoning process.",
    description="Start reasoning for a given session. The response is logged and not returned.",
    responses={
        200: {"description": "Reasoning task processed and logged."},
        500: {"description": "Error occurred during processing."},
    }
)
async def generate_response(request: ReasoningRequest):
    """
    Process a reasoning task for a given session and log the result.

    Args:
        request (ReasoningRequest): Contains the session_id for processing.

    Returns:
        dict: A message confirming task processing or an error.
    """
    session_id = request.session_id
    logging.info(f"Received request: session_id={session_id}")

    try:
        # Fetch previous beliefs and conversation history
        conversation_history = memory_tool.get_full_conversation(session_id=session_id)
        previous_beliefs = memory_tool.read_belief_state(session_id=session_id, num_to_retrieve=3)

        task = "Solve the task delegated from talker."
        while True:
            try:
                # Run reasoning task
                beliefs = reasoner.run(
                    task,
                    belief_states=previous_beliefs,
                    recent_conversation=conversation_history
                )
                beliefs = ast.literal_eval(beliefs)
                break
            except Exception as e:
                logging.error(f"Agent returned wrong format, retrying...")
                task += f"\nPrevious execution, your answer was wrong. Here is your output:\n\n{beliefs}"
        
        # Log and update shared memory
        logging.info(f"Reasoning task completed for session {session_id}: {beliefs}")
        result = memory_tool.update_belief_state(session_id=session_id, beliefs=beliefs, agent='reasoner')

        return {"message": f"Reasoning task completed and logged for session: {session_id} and Result: {result}"}

    except Exception as e:
        logging.error(f"Error in generate_response: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error in reasoning task: {str(e)}")