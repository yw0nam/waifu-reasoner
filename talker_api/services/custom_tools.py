from langchain_core.tools import tool

@tool
def request_solving_task(
    reasoner_status: str,
    task: str
) -> str:
    """
    Tool for delegating the task to reasoner.
    Args:
        reasoner_status: Status of reasoner
        task: Task to delegate to reasoner
    Returns:
        A string response indicating the result of the action based on the reasoner state.
    """
    if reasoner_status == 'IDLE':
        text = f"New task assigned: {task}"
    elif reasoner_status == 'RUNNING':
        text = "Task refused, reasoner are working for delegated task "
    elif reasoner_status == 'Error':
        text = "Task error. Request clarification from the user for the errored task."
    elif reasoner_status == 'WAITING':
        text = "Reasoner waiting for more information. Check the reasoner's belief state, request clarification or information about task."
    else:
        text = "UNIMPLEMENTED ERROR: Invalid reasoner state passed."
    return text


