from openai import OpenAI
import sys
from transformers.agents.llm_engine import MessageRole, get_clean_message_list
from transformers.agents import ReactCodeAgent, ManagedAgent
from transformers.agents.search import DuckDuckGoSearchTool, VisitWebpageTool

openai_role_conversions = {
    MessageRole.TOOL_RESPONSE: MessageRole.USER,
}

class OpenAIEngine:
    def __init__(self, url, token, temperature):
        self.client = OpenAI(
            base_url=url,
            api_key=token
        )
        self.temperature = temperature
    def __call__(self, messages, stop_sequences=[], max_token=4096):
        messages = get_clean_message_list(messages, role_conversions=openai_role_conversions)

        response = self.client.chat.completions.create(
            model='chat_model',
            messages=messages,
            max_tokens=max_token,
            stream=True,
        )
        # completion_str = ""
        # for chunk in response:
        #     try:
        #         content = chunk.choices[0].delta.content
        #         if type(content) == str:
        #             completion_str += content
        #             print(content, end='')  # Print without newline
        #             sys.stdout.flush()  # Ensure content is printed immediately
        #     except IndexError:
        #         pass
        # return completion_str
        response = self.client.chat.completions.create(
            model='chat_model',
            messages=messages,
            temperature=self.temperature,
            max_tokens=max_token,
            extra_body={
                "min_p": 0.1,
                "repetition_penalty": 1.1,
            },
            stop=['[/INST]', '<|im_end|>','</s>'],
        )
        return response.choices[0].message.content

def load_agents(engine, system):
    web_agent = ReactCodeAgent(
        tools=[DuckDuckGoSearchTool(), VisitWebpageTool()], llm_engine=engine
    )
    managed_web_agent = ManagedAgent(
        agent=web_agent,
        name="web_search_agent",
        description="Runs web searches for you. Give it your query as an argument."
    )

    reasnoer = ReactCodeAgent(
        tools=[], 
        llm_engine=engine, 
        system_prompt=system,
        managed_agents=[managed_web_agent],
        additional_authorized_imports=['ast']
    )
    return reasnoer