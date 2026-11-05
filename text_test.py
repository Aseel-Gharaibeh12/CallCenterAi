"""Ask the bot's brain questions by text (no microphone needed).

Uses the same instructions, company file and n8n logging as bot.py.
Run from the project folder:  .venv/bin/python text_test.py
"""

import asyncio
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bot  # loads .env, SYSTEM_PROMPT and send_unanswered_question
from groq import AsyncGroq

QUESTIONS = [
    "هل بتركّبوا كاميرات مراقبة؟",
    "هل بتقبلوا الدفع بالتقسيط؟",
    "قديش سعر طفاية ثاني أكسيد الكربون وزن ستة كيلو؟",
]

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "log_unanswered_question",
            "description": (
                "Record a customer question that the company information does not answer. "
                "Call this every time the customer asks something that is not covered by the "
                "company information, before telling them that you do not have that information."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "The customer's question, written clearly in Arabic as the customer asked it.",
                    }
                },
                "required": ["question"],
            },
        },
    }
]

MODEL = "openai/gpt-oss-120b"


async def ask(client, question, conversation_id):
    messages = [
        {"role": "system", "content": bot.SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]
    resp = await client.chat.completions.create(model=MODEL, messages=messages, tools=TOOLS)
    msg = resp.choices[0].message
    saved = None
    if msg.tool_calls:
        messages.append({"role": "assistant", "content": msg.content or "", "tool_calls": [tc.model_dump() for tc in msg.tool_calls]})
        for tc in msg.tool_calls:
            args = json.loads(tc.function.arguments or "{}")
            saved = await bot.send_unanswered_question(args.get("question", question), conversation_id, None)
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps({"saved": saved})})
        resp = await client.chat.completions.create(model=MODEL, messages=messages, tools=TOOLS)
        msg = resp.choices[0].message
    return msg.content or "", saved


async def main():
    if not os.getenv("GROQ_API_KEY"):
        print("GROQ_API_KEY is missing from .env")
        return
    client = AsyncGroq(api_key=os.environ["GROQ_API_KEY"])
    conversation_id = "text-test-" + datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    results = []
    for i, q in enumerate(QUESTIONS, 1):
        print(f"\n[{i}] الزبون: {q}")
        try:
            answer, saved = await ask(client, q, conversation_id)
        except Exception as e:
            print(f"    خطأ: {e}")
            results.append("ERROR")
            continue
        print(f"    المساعد: {answer.strip()}")
        if saved is True:
            print("    ✅ انحفظ بـ n8n")
            results.append("SAVED")
        elif saved is False:
            print("    ❌ الأداة اشتغلت بس n8n ما حفظ (شوف السطر اللي فوق)")
            results.append("N8N_FAILED")
        else:
            print("    ⚠️ المساعد ما استعمل الأداة")
            results.append("NO_TOOL")
    print("\nالنتيجة:", " | ".join(results))


asyncio.run(main())
