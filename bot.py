import os
from dotenv import load_dotenv
from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import LLMRunFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker, ProcessorUnusablePolicy
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import LLMContextAggregatorPair, LLMUserAggregatorParams
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import create_transport
from pipecat.services.groq.llm import GroqLLMService
from pipecat.services.groq.stt import GroqSTTService
from pipecat.services.groq.tts import GroqTTSService
from pipecat.transports.base_transport import BaseTransport, TransportParams
from pipecat.workers.runner import WorkerRunner
from pipecat.transcriptions.language import Language

load_dotenv(override=True)

# CONVERSATION_LOG: every finished call is saved in the "conversations" folder
import json
import re
import secrets
from datetime import datetime

CONVERSATIONS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "conversations")
_PHONE_RE = re.compile(r"[0-9٠-٩][0-9٠-٩\s\-]{6,}[0-9٠-٩]")
_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


def _msg_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(p.get("text", "") for p in content if isinstance(p, dict))
    return ""


def save_conversation(context, started_at):
    msgs = []
    for m in context.get_messages():
        if not isinstance(m, dict) or m.get("role") not in ("user", "assistant"):
            continue
        text = _msg_text(m.get("content")).strip()
        if text:
            msgs.append({"role": m["role"], "text": text})
    if not any(m["role"] == "user" for m in msgs):
        return  # nobody spoke, nothing worth saving
    phone = None
    for m in msgs:
        found = _PHONE_RE.search(m["text"]) if m["role"] == "user" else None
        if found:
            phone = re.sub(r"[\s\-]", "", found.group(0)).translate(_ARABIC_DIGITS)
            break
    ended_at = datetime.now()
    os.makedirs(CONVERSATIONS_DIR, exist_ok=True)
    cid = started_at.strftime("%Y-%m-%d_%H-%M-%S")
    data = {
        "id": cid,
        "started_at": started_at.isoformat(timespec="seconds"),
        "ended_at": ended_at.isoformat(timespec="seconds"),
        "phone": phone,
        "messages": msgs,
    }
    with open(os.path.join(CONVERSATIONS_DIR, cid + ".json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    with open(os.path.join(CONVERSATIONS_DIR, cid + ".txt"), "w", encoding="utf-8") as f:
        f.write(f"المحادثة: {started_at:%Y-%m-%d %H:%M}\n")
        if phone:
            f.write(f"رقم الزبون: {phone}\n")
        f.write("\n")
        for m in msgs:
            f.write(("الزبون: " if m["role"] == "user" else "المساعد: ") + m["text"] + "\n\n")
    logger.info(f"Conversation saved: conversations/{cid}.txt")


def _summary(data):
    start = datetime.fromisoformat(data["started_at"])
    end = datetime.fromisoformat(data.get("ended_at") or data["started_at"])
    users = [m["text"] for m in data["messages"] if m["role"] == "user"]
    return {
        "id": data["id"],
        "started_at": data["started_at"],
        "phone": data.get("phone"),
        "turns": len(data["messages"]),
        "duration_min": round((end - start).total_seconds() / 60, 1),
        "preview": (users[0] if users else "")[:90],
        "search": " ".join(m["text"] for m in data["messages"]) + " " + (data.get("phone") or ""),
    }


def list_conversations():
    items = []
    if os.path.isdir(CONVERSATIONS_DIR):
        for name in sorted(os.listdir(CONVERSATIONS_DIR), reverse=True):
            if name.endswith(".json"):
                try:
                    with open(os.path.join(CONVERSATIONS_DIR, name), encoding="utf-8") as f:
                        items.append(_summary(json.load(f)))
                except Exception as e:
                    logger.warning(f"Skipping {name}: {e}")
    return items


def get_conversation(cid):
    if not re.fullmatch(r"[0-9_\-]+", cid or ""):
        return None
    path = os.path.join(CONVERSATIONS_DIR, cid + ".json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    data["duration_min"] = _summary(data)["duration_min"]
    return data



# UNANSWERED_LOG: questions the bot cannot answer are sent to n8n
import aiohttp
from pipecat.adapters.llm.schemas.direct_function import tool_options
from pipecat.services.llm_service import FunctionCallParams

N8N_UNANSWERED_URL = os.getenv(
    "N8N_UNANSWERED_URL",
    "",
)


async def send_unanswered_question(question, conversation_id, phone):
    if not N8N_UNANSWERED_URL:
        logger.info(f"N8N_UNANSWERED_URL is not set - question not sent: {question}")
        return False
    payload = {"question": question, "conversation_id": conversation_id, "customer_phone": phone or ""}
    try:
        timeout = aiohttp.ClientTimeout(total=8)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(N8N_UNANSWERED_URL, json=payload) as resp:
                ok = resp.status == 200
                if ok:
                    logger.info(f"Unanswered question saved in n8n: {question}")
                else:
                    logger.warning(f"n8n answered {resp.status} for unanswered question: {await resp.text()}")
                return ok
    except Exception as e:
        logger.warning(f"Could not reach n8n to save the unanswered question: {e}")
        return False

COMPANY_INFO = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "company_info.txt"), encoding="utf-8").read()
SYSTEM_PROMPT = (
    "You are the voice customer-service assistant of Al-Mustaqbal Public Safety Company. "
    "Your replies are spoken aloud, so do not use emojis, lists, or formatting. "
    "Always reply in Arabic, in one or two short sentences. "
    "If the customer wants a booking, a price quote, or a call back, politely ask for their name and phone number. "
    "Answer only using the company information below. If the answer is not there, "
    "first call the log_unanswered_question tool with the customer's question, then "
    "say you do not have that information and give the company phone number.\n\n"
    + COMPANY_INFO
)

transport_params = {
    "webrtc": lambda: TransportParams(audio_in_enabled=True, audio_out_enabled=True),
}


async def run_bot(transport: BaseTransport, runner_args: RunnerArguments):
    logger.info("Starting bot")
    started_at = datetime.now()
    key = os.environ["GROQ_API_KEY"]
    stt = GroqSTTService(api_key=key, settings=GroqSTTService.Settings(language=Language.AR))
    llm = GroqLLMService(
        api_key=key,
        settings=GroqLLMService.Settings(
            model="openai/gpt-oss-120b",
            system_instruction=SYSTEM_PROMPT,
        ),
    )
    tts = GroqTTSService(api_key=key, settings=GroqTTSService.Settings(model="canopylabs/orpheus-arabic-saudi", voice="noura"))

    @tool_options(cancel_on_interruption=False, timeout_secs=15)
    async def log_unanswered_question(params: FunctionCallParams, question: str):
        """Record a customer question that the company information does not answer.

        Call this every time the customer asks something that is not covered by the
        company information, before telling them that you do not have that information.

        Args:
            question: The customer's question, written clearly in Arabic as the customer asked it.
        """
        phone = None
        for m in context.get_messages():
            if isinstance(m, dict) and m.get("role") == "user":
                found = _PHONE_RE.search(_msg_text(m.get("content")))
                if found:
                    phone = re.sub(r"[\s\-]", "", found.group(0)).translate(_ARABIC_DIGITS)
        saved = await send_unanswered_question(question, started_at.strftime("%Y-%m-%d_%H-%M-%S"), phone)
        await params.result_callback({"saved": saved})

    context = LLMContext(tools=[log_unanswered_question])
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context, user_params=LLMUserAggregatorParams(vad_analyzer=SileroVADAnalyzer())
    )
    pipeline = Pipeline([
        transport.input(), stt, user_aggregator, llm, tts, transport.output(), assistant_aggregator,
    ])
    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(enable_metrics=True, enable_usage_metrics=True),
        idle_timeout_secs=runner_args.pipeline_idle_timeout_secs,
        processor_unusable_policy=ProcessorUnusablePolicy.END,
    )
    runner = WorkerRunner(handle_sigint=runner_args.handle_sigint)
    await runner.add_workers(worker)

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        logger.info("Client connected")
        context.add_message({"role": "developer", "content": "Greet the user in Arabic as the Al-Mustaqbal company assistant, and mention briefly that the conversation is saved to improve the service."})
        await worker.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info("Client disconnected")
        await runner.cancel()

    try:
        await runner.run()
    finally:
        try:
            save_conversation(context, started_at)
        except Exception as e:
            logger.error(f"Could not save the conversation: {e}")


async def bot(runner_args: RunnerArguments):
    transport = await create_transport(runner_args, transport_params)
    await run_bot(transport, runner_args)


if __name__ == "__main__":
    from pipecat.runner.run import main

    # CUSTOM_UI: serve the redesigned interface (original stays at /client/)
    from fastapi.responses import FileResponse
    from pipecat.runner.run import app

    UI_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui", "index.html")

    @app.get("/", include_in_schema=False)
    async def custom_ui():
        return FileResponse(UI_FILE)

    # CUSTOM_UI_APP: same interface at http://localhost:7860/app/
    @app.get("/app", include_in_schema=False)
    @app.get("/app/", include_in_schema=False)
    async def custom_ui_app():
        return FileResponse(UI_FILE)

    # CUSTOM_UI_CLIENT: the new design also replaces the old page at /client/
    @app.get("/client", include_in_schema=False)
    @app.get("/client/", include_in_schema=False)
    async def custom_ui_client():
        return FileResponse(UI_FILE)

    # CUSTOM_ADMIN: review saved conversations at http://localhost:7860/admin
    # Set ADMIN_PASSWORD in .env to protect this page (needed on a public server).
    from fastapi import Depends, HTTPException
    from fastapi.security import HTTPBasic, HTTPBasicCredentials

    ADMIN_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui", "admin.html")
    _basic = HTTPBasic(auto_error=False)

    def _check_admin(creds: HTTPBasicCredentials | None = Depends(_basic)):
        password = os.getenv("ADMIN_PASSWORD")
        if not password:
            return
        if not creds or not secrets.compare_digest(creds.password, password):
            raise HTTPException(status_code=401, headers={"WWW-Authenticate": "Basic"})

    @app.get("/admin", include_in_schema=False, dependencies=[Depends(_check_admin)])
    @app.get("/admin/", include_in_schema=False, dependencies=[Depends(_check_admin)])
    async def admin_page():
        return FileResponse(ADMIN_FILE)

    @app.get("/admin/api/conversations", include_in_schema=False, dependencies=[Depends(_check_admin)])
    async def admin_list():
        return list_conversations()

    @app.get("/admin/api/conversations/{cid}", include_in_schema=False, dependencies=[Depends(_check_admin)])
    async def admin_get(cid: str):
        data = get_conversation(cid)
        if data is None:
            raise HTTPException(status_code=404)
        return data

    main()
