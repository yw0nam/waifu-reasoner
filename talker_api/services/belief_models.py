from pydantic import BaseModel, Field

class TalkerBeliefState(BaseModel):
    # """Response"""
    context: str = Field(..., description="Summarized context from conversation history, previous belief state, etc.")
    keywords_and_events: str = Field(..., description="The important words or event to keep remember.")
    current_state: str = Field(..., description="Current state of conversation. It can be a emotion or task state.. etc. e.g: 'Conversation', 'Understanding Task', 'Feel happy talking with master who is my love'")
    
class TalkerDelegateBeliefState(BaseModel):
    context: str = Field(..., description="Summarized context from conversation history, previous belief state, etc.")
    keywords_and_events: str = Field(..., description="The important words or event to keep remember.")
    delegated_task: str = Field(default='', description="Task that delegate to 'Reasoner'. Make sure rephrase, summmarize, filter the user task for good understanding to 'Reasoner'. If you are not delegate task to reasoner, Set as ''")

    
class ReasonerBeliefState(BaseModel):
    task: str = Field(..., description="Task to solve. Understand user's intend. Rephrase, filtering and summarize for better understanding.")