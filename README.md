# WaifuAssistant

![image](https://github.com/user-attachments/assets/1aafb125-2a7f-4481-a80c-cc021b7e8510)

The goal of this project is that our waifu recognize user's request and context and solve the task or chatting with given persona.


## feature

- Talker
- Reasoner

## WIP feature

- Replace Talker to agent based.
- Migrate overall implementation to [langgraph](https://www.langchain.com/langgraph)
- Recongnize User's screen 

# How to run

Clone server-side repository(this repository)

```bash
git clone https://github.com/yw0nam/waifu-reasoner
cd waifu-reasoner
```

You should adjust port, huggingface cache path, db path.. etc in docker-compose.yaml

After that,

```bash
docker-compose build
```

```bash
docker-compose up
```
