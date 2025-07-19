from utils.helpers import set_api_keys_env
set_api_keys_env()

from langgraph.graph import StateGraph, END
from typing import TypedDict, Annotated, List
import operator
from langgraph.checkpoint.memory import InMemorySaver
from langchain_core.messages import AnyMessage, SystemMessage, HumanMessage, ToolMessage
from langchain_openai import ChatOpenAI
from tavily import TavilyClient
from langchain_core.pydantic_v1 import BaseModel
from rich.console import Console
from rich.markdown import Markdown


class AgentState(TypedDict):
    task: str # This is the human input
    plan: str # Key to keep track of plan, planning agent will generate
    draft: str # draft of the essay
    critique: str # critique of the draft, critique agent
    content: List[str] # list of document that tavily has researched
    revision_number: int # number of revisions made to the draft
    max_revision: int # maximum number of revisions allowed

class Queries(BaseModel):
    queries: List[str]


model = ChatOpenAI(model="gpt-4o", temperature=0.0)

PLAN_PROMPT = """You are an expert writer tasked with writing high level outline of an essay. \
Write such an outline for the user provided topic. Give an outline of the essay along with any relevant notes \
    or instructions for the sections. \
"""

RESEARCH_PLAN_PROMPT = """You are a researcher charged with providing information that can \
be used when writing the following essay. Generate a list of search queries that will gather \
any relevant information. Only generate 3 queries max."""

WRITER_PROMPT = """You are an essay assistant tasked with writing excellent 5-paragraph essays. \
Generate the best essay possible fo rthe user's request and the initial outline. \
If the user provides critique, respond with a revised version of your previous attempts. \
Utilize all the information below as needed:

------
{content}"""

REFLECTION_PROMPT = """You are a teacher grading an essay submission. \
Generate critique and recommendations for the user's submission. \
Provide detailed recommendations, including requests for length, depth, style, etc."""

RESEARCH_CRITIQUE_PROMPT = """You are a researcher charged with providing information that can \
be used when making any requested revisions (as outlined below). \
Generate a list of search queries that will gather any releavant information. Only generate 3 queries max."""

def plan_node(state: AgentState):
    messages = [
        SystemMessage(content=PLAN_PROMPT),
        HumanMessage(content=state["task"]),
    ]
    response = model.invoke(messages)
    return {"plan": response.content}


def research_plan_node(state:AgentState):
    queries = model.with_structured_output(Queries).invoke([
        SystemMessage(content=RESEARCH_PLAN_PROMPT),
        HumanMessage(content=state["task"]),
    ])
    content = state.get('content', [])
    for q in queries.queries:
        response = tavily.search(q, max_results=3)
        for result in response['results']:
            content.append(result['content'])
    return {"content": content}


def generate_node(state:AgentState):
    content = "\n\n".join(state.get('content', []))
    user_message = HumanMessage(content = f"{state['task']}\n\nHere is my plan:\n\n{state['plan']}")
    messages = [
        SystemMessage(
            content=WRITER_PROMPT.format(content=content)
        ),
        user_message
    ]
    resoponse = model.invoke(messages)
    return {
        "draft": resoponse.content, 
        "revision_number": state.get("revision_number", 1) + 1
    }


def reflection_node(state: AgentState):
    messages = [
        SystemMessage(content=REFLECTION_PROMPT),
        HumanMessage(content=state["draft"]),
    ]
    response = model.invoke(messages)
    return {"critique": response.content}


def research_critique_node(state: AgentState):
    queries = model.with_structured_output(Queries).invoke([
        SystemMessage(content=RESEARCH_CRITIQUE_PROMPT),
        HumanMessage(content=state["critique"]),
    ])
    content = state['content'] or []
    for q in queries.queries:
        response = tavily.search(q, max_results=3)
        for result in response['results']:
            content.append(result['content'])
    return {"content": content}


def should_continue(state):
    if state['revision_number'] >= state['max_revision']:
        return END
    return "reflect"


tavily = TavilyClient()
inmem1 = InMemorySaver()

# Create the state graph and add nodes
builder= StateGraph(AgentState)

# define the nodes
builder.add_node("planner", plan_node)
builder.add_node("research_plan", research_plan_node)
builder.add_node("generate", generate_node)
builder.add_node("reflect", reflection_node)
builder.add_node("research_critique", research_critique_node)

# define the entry point
builder.set_entry_point("planner")

# define the edges
builder.add_conditional_edges(
    "generate",
    should_continue,
    {END:END, "reflect": "reflect"}
)
builder.add_edge("planner", "research_plan")
builder.add_edge("research_plan", "generate")

builder.add_edge("reflect",  "research_critique")
builder.add_edge("research_critique", "generate")

# compile the graph
graph = builder.compile(checkpointer=inmem1)

if __name__ == "__main__":
    thread1 = {"configurable": {"thread_id": "1"}}

    for s in graph.stream({
        "task": "What happened in Air-India Flight 171 crash happened in 2025",
        "max_revision": 2,
        "revision_number": 0,
    }, thread1):
        print(s)

    console = Console()
    console.print("# Essay Draft", style="bold underline")
    console.print(Markdown(s['generate']['draft']))

