from pymongo import MongoClient
from transformers.agents import Tool
from langchain_core.messages import AIMessage, ToolMessage
from datetime import datetime
from pytz import timezone
class SharedMemoryManagerTool(Tool):
    name = "shared_memory_manager"
    description = "Tool for managing shared memory, including belief state and conversation history."

    inputs = {
        "query": {
            "type": "string",
            "description": (
                "The action to perform. Options include:\n"
                "1. 'update_belief_state' - Update belief state with a dictionary. (Requires: session_id, beliefs, agent).\n"
                "   Output: A confirmation message indicating whether the belief state was updated successfully. "
                "2. 'read_belief_state' - Retrieve belief state values for an agent. (Requires: session_id, Optional: num_to_retrieve).\n"
                "   Output: A string representation of the retrieved belief state(s). "
                "3. 'get_all_beliefs' - Retrieve all belief state values for a given session. (Requires: session_id).\n"
                "   Output: A string representation of all beliefs for the session. "
                # "4. 'add_conversation_message' - Store a message in the conversation history. (Requires: session_id, role, content).\n"
                # "   Output: A confirmation message indicating whether the message was stored successfully. Default: None.\n"
                "4. 'get_recent_messages' - Retrieve the most recent messages from the conversation history. (Requires: session_id, Optional: num_to_retrieve).\n"
                "   Output: A string representation of the retrieved recent messages. "
                "5. 'get_full_conversation' - Retrieve the entire conversation history from the database. (Requires: session_id).\n"
                "   Output: A string representation of the full conversation history. "
                # "7. 'check_and_update_reasoner' - Check if the Reasoner is running, update its status, and set pending query. (Requires: session_id, beliefs).\n"
                # "   Output: A message indicating the Reasoner's status and task assignment."
                # "8. 'get_persona' - Retrieve persona. (Requires: No parameter required).\n"
                # "   Output: The stored persona as a string. "
            )
        },
        "session_id": {
            "type": "string",
            "description": "A unique identifier for the session."
        },
        "beliefs": {
            "type": "any",
            "description": "A dictionary containing key-value pairs for belief states. Default: None."
        },
        # "role": {
        #     "type": "string",
        #     "description": "The role of the message sender in the conversation ('user','assistant' or 'system'). Default: None."
        # },
        # "content": {
        #     "type": "string",
        #     "description": "The content of the message being stored in the conversation history. Default: None."
        # },
        "num_to_retrieve": {
            "type": "integer",
            "description": "The number of recent messages or belief states to retrieve. Defaults to 5."
        },
        "agent": {
            "type": "string",
            "description": "The agent responsible for updating beliefs ('talker' or 'reasoner'). Default: ""."
        }
    }
    output_type = "string"

    def __init__(self, mongo_uri: str = "mongodb://root:1234@localhost:27017", db_name: str = "my_chat_db"):
        self.client = MongoClient(mongo_uri)
        self.db = self.client[db_name]
        self.belief_collection = self.db["belief_state"]
        self.convo_collection = self.db["conversation_history"]

    def forward(self, query: str, session_id: str, beliefs: dict = None, agent: str = "", role: str = None, content: str = None, num_to_retrieve: int = 5):
        try:
            if query == "update_belief_state":
                return self.update_belief_state(session_id, beliefs, agent)
            elif query == "read_belief_state":
                return self.read_belief_state(session_id, num_to_retrieve)
            elif query == "get_all_beliefs":
                return self.get_all_beliefs(session_id)
            elif query == "add_conversation_message":
                return self.add_conversation_message(session_id, role, content)
            elif query == "get_recent_messages":
                return self.get_recent_messages(session_id, num_to_retrieve)
            elif query == "get_full_conversation":
                return self.get_full_conversation(session_id)
            elif query == "check_and_update_reasoner":
                return self.check_and_update_reasoner(session_id, beliefs)
            elif query == "get_persona":
                return self.get_persona(session_id)
            else:
                return "Unknown query type."
        except Exception as e:
            return f"An error occurred: {str(e)}"

    def initialize(self, session_id: str, system_content: str = "") -> str:
        """
        Initializes the belief state and conversation history for a session.
        This ensures the session starts with a clean state.

        Parameters:
        - session_id: The unique identifier for the session.

        Returns:
        - A confirmation message indicating successful initialization.
        """
        try:
            self.belief_collection.update_one(
                {"session_id": session_id},
                {"$set": {
                        "talker": [], 
                        "reasoner": [
                            {"dicts": {"status": "IDLE", "task": "Not assigned"}, "timestamp": datetime.now(timezone('Asia/Seoul')).isoformat()}
                        ],
                    },
                },
                upsert=True
            )
            self.convo_collection.update_one(
                {"session_id": session_id},
                {"$set": {"conversations": [{'role': 'system', 'content': system_content, "timestamp": datetime.now(timezone('Asia/Seoul')).isoformat() }]}},
                upsert=True
            )
            return f"Session {session_id} initialized successfully."
        except Exception as e:
            return f"Failed to initialize session {session_id}: {str(e)}"
    # ------------------------------------------------------------------------
    # BELIEF STATE METHODS
    # ------------------------------------------------------------------------
    def get_persona(self, session_id) -> str:
        doc = self.convo_collection.find_one({"session_id": session_id})
        persona = doc.get("conversations", [])[0].get("content", "")
        return persona
    def update_belief_state(self, session_id: str, beliefs: dict, agent: str) -> str:
        if agent not in ["talker", "reasoner"]:
            return "Invalid agent specified. Please use 'talker' or 'reasoner'."

        new_belief = {
            "dicts": beliefs,
            "timestamp": datetime.now(timezone('Asia/Seoul')).isoformat()
        }

        try:
            self.belief_collection.update_one(
                {"session_id": session_id},
                {"$push": {agent: new_belief}},
                upsert=True
            )
            return f"Belief state for {agent} updated."
        except Exception as e:
            return f"Failed to update belief state: {str(e)}"

    def read_belief_state(self, session_id: str, num_to_retrieve: int = 1) -> dict:
        try:
            doc = self.belief_collection.find_one({"session_id": session_id})
            if not doc:
                return {}

            result = {}
            if "talker" in doc:
                result["talker"] = [belief["dicts"] for belief in doc["talker"][-num_to_retrieve:]]
            if "reasoner" in doc:
                result["reasoner"] = [belief["dicts"] for belief in doc["reasoner"][-num_to_retrieve:]]

            return result
        except Exception as e:
            return {"error": f"Failed to read belief state: {str(e)}"}

    def get_all_beliefs(self, session_id: str) -> dict:
        try:
            doc = self.belief_collection.find_one({"session_id": session_id})
            if not doc:
                return "No beliefs found for this session."
            return doc
        except Exception as e:
            return f"Failed to retrieve all beliefs: {str(e)}"

    def add_conversation_message(self, session_id: str, role: str, content: str|dict) -> str:
        role = role.lower()

        new_message = {
            "role": role,
            "content": content,
            "timestamp": datetime.now(timezone('Asia/Seoul')).isoformat()
        }

        try:
            self.convo_collection.update_one(
                {"session_id": session_id},
                {"$push": {"conversations": new_message}},
                upsert=True
            )
            return "Message stored successfully."
        except Exception as e:
            return f"Failed to store message: {str(e)}"

    def get_recent_messages(self, session_id: str, num_to_retrieve: int = 5) -> list:
        try:
            doc = self.convo_collection.find_one({"session_id": session_id})
            if not doc or "conversations" not in doc:
                return "No messages found for this session."

            all_msgs = doc.get("conversations", [])
            recent_msgs = all_msgs[-num_to_retrieve:]
            if recent_msgs[0]['role'] != 'system':
                recent_msgs = [{'role': 'system', 'content': self.get_persona(session_id=session_id)}] + recent_msgs
            recent_msgs = self.parsing_message(recent_msgs)
            return recent_msgs
        except Exception as e:
            return f"Failed to retrieve recent messages: {str(e)}"

    def get_full_conversation(self, session_id: str) -> list:
        try:
            doc = self.convo_collection.find_one({"session_id": session_id})
            if not doc:
                return "Session not found."
            messages = doc.get("conversations", [])
            messages = self.parsing_message(messages)
            return messages
        except Exception as e:
            return f"Failed to retrieve full conversation: {str(e)}"

    def check_and_update_reasoner(self, session_id: str, beliefs: dict) -> str:
        try:
            doc = self.belief_collection.find_one({"session_id": session_id})
            if not doc:
                return "Session not found."

            if "reasoner" in doc:
                latest_reasoner_belief = doc["reasoner"][-1]["dicts"] if doc["reasoner"] else None
                if latest_reasoner_belief and latest_reasoner_belief.get("status") != "IDLE":
                    return f"Reasoner is not idle. Current status: {latest_reasoner_belief.get('status')}. Details: {latest_reasoner_belief}"

            new_belief = {
                "dicts": {**beliefs, "status": "RUNNING"},
                "timestamp": datetime.now(timezone('Asia/Seoul')).isoformat()
            }

            self.belief_collection.update_one(
                {"session_id": session_id},
                {"$push": {"reasoner": new_belief}},
                upsert=True
            )

            return f"Reasoner has started processing. beliefs: {beliefs}"
        except Exception as e:
            return f"Failed to update Reasoner: {str(e)}"
    def parsing_message(self, messages: list):
        for i, message in enumerate(messages):
            if type(message['content']) == dict:
                data = message['content']
                if message['role'] == 'assistant':
                    messages[i] = AIMessage(
                        content=data['content'],
                        additional_kwargs=data['additional_kwargs'],
                        metadata=data.get('response_metadata', {}),
                        tool_calls=data['tool_calls'],
                    )
                elif message['role'] == 'tool':
                    messages[i] = ToolMessage(
                        content=data['content'],
                        name=data['name'],
                        tool_call_id=data['tool_call_id'],
                        metadata=data.get('response_metadata', {}),
                        additional_kwargs=data['additional_kwargs'],
                        status=data['status']
                    )
        return messages