import sys
from langchain_core.messages.tool import ToolMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel
from services.memory_tool import SharedMemoryManagerTool
from services.belief_models import TalkerBeliefState, TalkerDelegateBeliefState
import json

def mapping_function(x):
    if type(x) == ToolMessage:
        return f"ROLE: tool\nMessage: {x.content}"
    elif type(x) == dict: # Typical chat template 
        return f"ROLE: {x['role']}\nMessage: {x['content']}"
    elif x.tool_calls:
        return f"ROLE: tool_call\nMessage: {x.tool_calls[0]}"
        
def store_belief_and_conversation(llm: ChatOpenAI, memory_manager: SharedMemoryManagerTool, session_id, user_query, previous_belief_states, history, response_list):
        
    string_conversation_history = "\n".join(list(map(lambda x: mapping_function(x), history[1:])))
    # print(memory_manager.update_belief_state(session_id=session_id, beliefs=belief_state, agent='talker'))
    print(memory_manager.add_conversation_message(session_id=session_id, role='user', content=user_query))
        
    #TODO Multi tool call supporting?
    if len(response_list) == 1:
        print(memory_manager.add_conversation_message(session_id=session_id, role='assistant', content=response_list[0]['content']))
    elif len(response_list) == 3:
        # belief_state = generate_belief_state(llm, output_structure=ReasonerBeliefState, user_query=user_query, previous_belief=previous_belief_states, conversation_history=string_conversation_history)
        # belief_state = belief_state.model_dump()
        # belief_state.update({'user_query': user_query})
        belief_state = generate_belief_state(llm, output_structure=TalkerDelegateBeliefState, user_query=user_query, previous_belief=previous_belief_states, conversation_history=string_conversation_history)
        belief_state = belief_state.model_dump()
        print(memory_manager.check_and_update_reasoner(session_id=session_id, beliefs=belief_state))
        print(memory_manager.add_conversation_message(session_id=session_id, role='assistant', content=response_list[0].model_dump()))
        print(memory_manager.add_conversation_message(session_id=session_id, role='tool', content=response_list[1].model_dump()))
        print(memory_manager.add_conversation_message(session_id=session_id, role='assistant', content=response_list[2]['content']))
    else:
        raise NotImplementedError("Length of response should be 1 or 3")

def generate_belief_state(llm: ChatOpenAI, output_structure: BaseModel, user_query: str, previous_belief: str, conversation_history):
    prompt = [
        {
            'role': 'system',
            'content': "You are expert of generate belief state that represent current state."
        },
        {
            'role': 'user',
            'content': f"""Generate a belief state corresponding conversation history and task. 
        
Here is the Guildline:
• belief state is a dictionary that containing key-value pairs for better understanding of conversation flow.
• You filter, summarize, and rephrase user's query and conversation history. Making them clear and actionable for the agent.
• You must keep dictionary key-value format, otherwise, you got error. 

### USER QUERY: 
{user_query}

### PREVIOUS BELIEF STATES:
{previous_belief}

### CONVERSATION HISTORY:
{conversation_history}"""
        }
    ]
    structured_llm = llm.with_structured_output(output_structure)
    return structured_llm.invoke(prompt)

async def talker_completion_request(
    llm: ChatOpenAI, history: list, tools_dict: dict, reasoner_status: str
):
    response_text = ""
    tool_not_detected = True
    tool_call = None
    response_list = []
    # try:
    async for chunk in llm.astream(history):
        # Process content if available
        if chunk.content and chunk.additional_kwargs == {}:
            if chunk.content != 'ool_call>':
                response_text += chunk.content
                # print(chunk.content, end='')  # Print without newline
                # sys.stdout.flush()  # Ensure content is printed immediately
                yield f"event:token\ndata: {json.dumps(chunk.model_dump(), ensure_ascii=False)}\n\n"
        # Check for tool call information in additional_kwargs
        elif chunk.tool_call_chunks:
            if tool_not_detected:
                tool_call = chunk
                tool_not_detected = False
            else:
                # Handle concatenation explicitly if necessary
                tool_call = tool_call + chunk  # Ensure this operation works

    if not tool_call: 
        history.append({'role': 'assistant', 'content': response_text})
        response_list.append({'role': 'assistant', 'content': response_text})
    if tool_call:
        tool_calls = getattr(tool_call, 'tool_calls', [])
        if tool_calls:
            tool_name = tool_calls[0].get('name', '').lower()  # Safe access
            selected_tool = tools_dict.get(tool_name)

            if not selected_tool:
                print(f"Tool '{tool_name}' not found.")
            else:
                if tool_name == 'request_solving_task':
                    tool_calls[0]['args'].update({
                        'status' : reasoner_status
                    })
                    tool_msg = selected_tool.invoke(tool_calls[0])
                tool_msg = selected_tool.invoke(tool_calls[0])
                history.extend([tool_call, tool_msg])
                response_list.extend([tool_call, tool_msg])
                response_text = ""

            async for chunk in llm.astream(history):
                if chunk.content:
                    response_text += chunk.content
                    # print(chunk.content, end='')  # Print without newline
                    # sys.stdout.flush()  # Ensure content is printed immediately
                    yield f"event:token\ndata: {json.dumps(chunk.model_dump(), ensure_ascii=False)}\n\n"

            history.append({'role': 'assistant', 'content': response_text})
            response_list.append({'role': 'assistant', 'content': response_text})
    yield f"event:final_result\ndata: {json.dumps({'history': history, 'response_list': response_list}, ensure_ascii=False)}\n\n"

async def add_conversation(llm, user_query, tools, tools_dict, conversation_history: list, previous_beliefs: dict):

    reasoner_belief = parse_reasoner_to_string(previous_beliefs)
    conversation_history[0]['content'] += f"\n\## Current_Belief_state:\n{reasoner_belief}"
    conversation_history.append({
        'role': 'user',
        'content': user_query
    })
    reasoner_status = previous_beliefs['reasoner'][-1]['status']
    llm_with_tools = llm.bind_tools(tools)
    conversation_history, response_list = await talker_completion_request(
        llm_with_tools, 
        history=conversation_history, 
        tools_dict=tools_dict, 
        reasoner_status=reasoner_status
    )
    return conversation_history, response_list

def parse_reasoner_to_string(data):
    result = []
    if 'reasoner' in data:
        for entry in data['reasoner']:
            result.append(f"Reasoner:")
            result.append(f"- Context: {entry.get('context', 'N/A')}")
            result.append(f"- Keywords and Events: {entry.get('keywords_and_events', 'N/A')}")
            result.append(f"- Current State: {entry.get('current_state', 'N/A')}")
            result.append(f"- Delegated Task: {entry.get('delegated_task', 'N/A')}")
            result.append(f"- Status: {entry.get('status', 'N/A')}")
    return "\n".join(result)