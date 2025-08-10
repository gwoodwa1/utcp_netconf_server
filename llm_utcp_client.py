import asyncio
import json
import os
import re
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

import gradio as gr
from dotenv import load_dotenv
from utcp.client.utcp_client import UtcpClient
from utcp.client.utcp_client_config import UtcpClientConfig, UtcpDotEnv
from utcp.shared.tool import Tool
import openai


# -------------------------
# Config / Init
# -------------------------
ROOT = Path(__file__).resolve().parent
PROVIDERS = str(ROOT / "providers.json")
ENV_FILE = str(ROOT / ".env")  # optional but recommended

load_dotenv(ENV_FILE)

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY not set. Put it in .env or export it.")

oai = openai.AsyncOpenAI(api_key=OPENAI_API_KEY)

# Created once at startup
_utcp_client: Optional[UtcpClient] = None


# -------------------------
# UTCP helpers
# -------------------------
async def init_utcp() -> UtcpClient:
    global _utcp_client
    if _utcp_client:
        return _utcp_client

    cfg = UtcpClientConfig(
        providers_file_path=PROVIDERS,
        load_variables_from=[UtcpDotEnv(env_file_path=ENV_FILE)],
    )
    _utcp_client = await UtcpClient.create(cfg)
    return _utcp_client


async def discover_tools(client: UtcpClient, query: str = "netconf", limit: int = 50) -> List[Tool]:
    return await client.search_tools(query, limit=limit)


def tools_to_json_for_prompt(tools: List[Tool]) -> str:
    """Serialize tools as JSON so the LLM can see exact names + arg schemas."""
    return json.dumps([t.model_dump() for t in tools], indent=2)


# -------------------------
# LLM prompts
# -------------------------
TOOL_CALL_SYSTEM = (
    "You are a careful network automation assistant.\n"
    "You have access to a set of tools via UTCP. When a tool is needed, you MUST reply with ONLY a JSON object\n"
    "containing exactly two keys: 'tool_name' and 'arguments' (arguments must be a JSON object). No other text.\n"
    'Example: {"tool_name": "netconf_tools.netconf_get_config", "arguments": {"host":"1.2.3.4", "source":"running"}}\n\n'
    "Here are the available tools (names, descriptions, and JSON argument schemas):\n"
)

FINAL_ANSWER_SYSTEM = (
    "You are a helpful assistant. Use the provided tool output to answer the user's request concisely and clearly.\n"
    "If the tool failed, explain the error and suggest the next troubleshooting step.\n"
)

def build_tool_call_messages(history, tools_json: str):
    content = f"{TOOL_CALL_SYSTEM}{tools_json}\n"
    msgs = [{"role": "system", "content": content}]
    for role, content in history:
        msgs.append({"role": role, "content": content})
    return msgs


def build_final_messages(history: List[Tuple[str, str]], tool_output: str) -> List[Dict[str, str]]:
    msgs = [{"role": "system", "content": FINAL_ANSWER_SYSTEM}]
    for role, content in history:
        msgs.append({"role": role, "content": content})
    msgs.append({"role": "user", "content": f"Tool output:\n{tool_output}\n\nPlease answer the original request using this output."})
    return msgs


async def chat_complete(messages: List[Dict[str, str]]) -> str:
    resp = await oai.chat.completions.create(
        model=OPENAI_MODEL,
        messages=messages,
        temperature=0.2,
    )
    return resp.choices[0].message.content or ""


TOOL_JSON_RE = re.compile(r"```json\s*({.*?})\s*```", re.DOTALL)

def extract_tool_json(s: str) -> Optional[Dict[str, Any]]:
    m = TOOL_JSON_RE.search(s)
    if not m:
        # fallback: first {...} block
        m = re.search(r"(\{[\s\S]*\})", s)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except Exception:
        return None


# -------------------------
# Orchestration per user query
# -------------------------
async def handle_user_query(user_text: str, state_history: List[Tuple[str, str]]) -> Tuple[str, str, str, List[Tuple[str, str]]]:
    """
    Returns (assistant_tool_json, tool_result_text, final_answer, updated_history)
    """
    client = await init_utcp()
    tools = await discover_tools(client, "netconf", limit=50)
    tools_json = tools_to_json_for_prompt(tools)

    # Step 1: Ask model for a tool call (JSON only)
    history = state_history.copy()
    history.append(("user", user_text))
    msgs_tool = build_tool_call_messages(history, tools_json)
    assistant_raw = await chat_complete(msgs_tool)
    tool_obj = extract_tool_json(assistant_raw)

    if not tool_obj or "tool_name" not in tool_obj or "arguments" not in tool_obj:
        # No tool chosen; just present the model's text
        history.append(("assistant", assistant_raw))
        return (assistant_raw, "(no tool called)", assistant_raw, history)

    # Step 2: Execute the tool
    tool_name = tool_obj["tool_name"]
    arguments = tool_obj["arguments"]
    try:
        tool_result = await client.call_tool(tool_name, arguments)
        tool_result_text = json.dumps(tool_result, indent=2)
    except Exception as e:
        tool_result_text = f"Tool call error for {tool_name} with args {arguments}:\n{str(e)}"

    # Add both the initial assistant tool JSON and the result to the visible history
    history.append(("assistant", json.dumps(tool_obj, indent=2)))

    # Step 3: Ask model for final answer using tool output
    msgs_final = build_final_messages(history, tool_result_text)
    final_answer = await chat_complete(msgs_final)
    history.append(("assistant", final_answer))

    return (json.dumps(tool_obj, indent=2), tool_result_text, final_answer, history)


# -------------------------
# Gradio UI
# -------------------------
with gr.Blocks(title="UTCP + OpenAI + NETCONF") as demo:
    gr.Markdown("## UTCP + OpenAI + NETCONF (Arista/EOS via FastAPI)")

    with gr.Row():
        user_box = gr.Textbox(label="Your request", placeholder="e.g., Show Ethernet1 config on 172.29.151.7 or set description…", lines=3)
    with gr.Row():
        submit = gr.Button("Run")
        clear = gr.Button("Clear")

    chat = gr.Chatbot(label="Conversation")
    tool_json_out = gr.Code(label="Assistant tool JSON", language="json")
    tool_result_out = gr.Code(label="Tool result", language="json")
    final_answer_out = gr.Markdown(label="Final answer")

    state = gr.State(value=[])

    async def on_submit(user_text, st):
        assistant_tool_json, tool_result_text, final_answer, new_state = await handle_user_query(user_text, st or [])
        # Build a compact chat transcript
        chat_pairs = []
        tmp_state = st.copy() if st else []
        tmp_state.append(("user", user_text))
        # Show assistant tool JSON line in chat for transparency
        tmp_state.append(("assistant", f"Proposed tool call:\n```json\n{assistant_tool_json}\n```"))
        tmp_state.append(("assistant", final_answer))
        # Convert to Chatbot format
        for i in range(0, len(tmp_state), 2):
            user_msg = tmp_state[i][1] if i < len(tmp_state) and tmp_state[i][0] == "user" else ""
            asst_msg = tmp_state[i+1][1] if i+1 < len(tmp_state) and tmp_state[i+1][0] == "assistant" else ""
            if user_msg or asst_msg:
                chat_pairs.append([user_msg, asst_msg])
        return chat_pairs, assistant_tool_json, tool_result_text, final_answer, new_state

    submit.click(
        on_submit,
        inputs=[user_box, state],
        outputs=[chat, tool_json_out, tool_result_out, final_answer_out, state],
    )

    def on_clear():
        return [], "", "", "", []

    clear.click(on_clear, outputs=[chat, tool_json_out, tool_result_out, final_answer_out, state])

if __name__ == "__main__":
    # Make sure the UTCP client is ready before launching Gradio
    asyncio.run(init_utcp())
    demo.launch(server_name="0.0.0.0", server_port=7860)
