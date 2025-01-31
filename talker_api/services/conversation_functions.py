from langchain_core.messages import AIMessage, ToolMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel
from services.memory_tool import SharedMemoryManagerTool
from services.belief_models import TalkerDelegateBeliefState
import json, logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")        

def store_belief_and_conversation(llm: ChatOpenAI, memory_manager: SharedMemoryManagerTool, session_id, user_query, previous_belief_states, history, response_list):
    # def mapping_function(x):
    #     if x['role'] == 'assistant':
    #         if type(x['content']) == str:
    #             return f"ROLE: {x['role']}\nMessage: {x['content']}"
    #         elif type(x['content']) == dict:
    #             return f"ROLE: {x['role']}\nMessage: {x['tool_calls']}"
    #     elif x['role'] == ''
    # print(memory_manager.add_conversation_message(session_id=session_id, role='user', content=user_query))
        
    #TODO Multi tool call supporting?
    if len(response_list) == 1:
        print(memory_manager.add_conversation_message(session_id=session_id, role='assistant', content=response_list[0]['content']))
    elif len(response_list) == 3:
        # string_conversation_history = "\n".join(list(map(lambda x: f"ROLE: {x['role']}\nMessage: {x['content'] if 'content' in x else x['tool_calls'] }", history[1:])))
        belief_state = generate_belief_state(llm, output_structure=TalkerDelegateBeliefState, user_query=user_query, previous_belief=previous_belief_states)#, conversation_history=string_conversation_history)
        belief_state = belief_state.model_dump()
        print(memory_manager.check_and_update_reasoner(session_id=session_id, beliefs=belief_state))
        for response in response_list:
            print(memory_manager.add_conversation_message(session_id=session_id, role=response['role'], content=response['content']))
    else:
        raise ValueError("Length of response should be 1 or 3")

def generate_belief_state(llm: ChatOpenAI, output_structure: BaseModel, user_query: str, previous_belief: str):
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
{previous_belief}"""
        }
    ]
    structured_llm = llm.with_structured_output(output_structure)
    return structured_llm.invoke(prompt)

async def talker_completion_request(
    llm: ChatOpenAI, history: list, tools_dict: dict, reasoner_status: str
):
    # prompt = parsing_message_for_langchain(history)
    response_text = ""
    tool_not_detected = True
    tool_call = None
    response_list = []
    async for chunk in llm.astream(history):
        # Process content if available
        if chunk.content and chunk.additional_kwargs == {}:
            if chunk.content != 'ool_call>':
                response_text += chunk.content
            
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
                tool_ls = [
                    {
                        'role': 'assistant',
                        **tool_call.model_dump()
                    },
                    {
                        'role': 'tool',
                        **tool_msg.model_dump()
                    },
                ]
                history.extend(tool_ls)
                response_list.extend(tool_ls)
                response_text = ""

            async for chunk in llm.astream(history):
                if chunk.content:
                    response_text += chunk.content
                    yield f"event:token\ndata: {json.dumps(chunk.model_dump(), ensure_ascii=False)}\n\n"

            history.append({'role': 'assistant', 'content': response_text})
            response_list.append({'role': 'assistant', 'content': response_text})
    yield f"event:final_result\ndata: {json.dumps({'history': history, 'response_list': response_list}, ensure_ascii=False)}\n\n"

def parse_reasoner_belief(data):
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

from langchain_core.messages import AIMessage, ToolMessage

def parsing_message_for_langchain(messages: list):
    out_list = []  # This will hold the parsed messages
    for message in messages:
        if isinstance(message.get("content"), dict):  # When the content is a dict
            data = message["content"]
            if message["role"] == "assistant":
                out_list.append(AIMessage(
                    content=data.get("content", ""),
                    additional_kwargs=data.get("additional_kwargs", {}),
                    metadata=data.get("response_metadata", {}),
                    tool_calls=data.get("tool_calls", [])
                ))
            elif message["role"] == "tool":
                out_list.append(ToolMessage(
                    content=data.get("content", ""),
                    name=data.get("name", ""),
                    tool_call_id=data.get("tool_call_id", ""),
                    metadata=data.get("response_metadata", {}),
                    additional_kwargs=data.get("additional_kwargs", {}),
                    status=data.get("status", "unknown")
                ))
            else:
                # For unexpected roles with dict content, fallback to dict
                out_list.append(message)
        else:
            # Append plain messages directly
            out_list.append(message)
    return out_list