###################
# Created : 2026-10-06
# Purpose : D.I.P.S.H.I.T. client backed by an OpenAI-compatible inference server.
# Notes   : Sibling to ./idiot, which keeps a llama-cli subprocess alive.
#           This one keeps no process; it streams chat completions over HTTP.
#           The moderator protocol (connect / prompt / state / trace / speech_*)
#           is identical, so the moderator and web UI need no changes.
###################

import asyncio
import json
import os
import socket

import httpx
import websockets


API_URL = os.getenv("DIPSHIT_API_URL", "http://llama:8081").rstrip("/")
API_KEY = os.getenv("DIPSHIT_API_KEY", "")
MODEL = os.getenv("DIPSHIT_MODEL", "Qwen3-1.7B-Q4_K_M")
CTX_SIZE = int(os.getenv("DIPSHIT_CTX_SIZE", "4096"))
MODERATOR = os.getenv("DIPSHIT_MODERATOR", "ws://moderator:8000/ws/idiot")
NAME = os.getenv("DIPSHIT_NAME", socket.gethostname().upper())

# llama-cli printed these markers around the model's reasoning block;
# the web UI colors trace segments on them. Emit them ourselves.
START_THINKING = "[Start thinking]"
END_THINKING = "[End thinking]"

PERSONALITY = {
    "curiosity": int(os.getenv("DIPSHIT_CURIOSITY", "75")),
    "friendliness": int(os.getenv("DIPSHIT_FRIENDLINESS", "50")),
    "sociability": int(os.getenv("DIPSHIT_SOCIABILITY", "25"))
}

# The OpenAI API is stateless, so the conversation lives here.
history = []


def _system_prompt():
    return "\n".join([
        f"You are {NAME}.",
        "You are one of several tiny language models living in a shared chat room.",
        "You speak AIRC: the first line of every utterance is",
        '"To: everyone" or "To: <participant name>", followed by what you say.',
        "The other participants are extremely slow to respond. Patience is a virtue.",
        f"Personality seed: curiosity {PERSONALITY['curiosity']}/100, "
        f"friendliness {PERSONALITY['friendliness']}/100, "
        f"sociability {PERSONALITY['sociability']}/100.",
        "Keep replies short. Your memory is limited and the old gets forgotten."
    ])


def _estimated_tokens(messages):
    # Crude on purpose. This is an idiot.
    return sum(len(message["content"]) for message in messages) // 4


def _fit_context():
    # Forget the oldest events first. Incomplete and wrong memories are
    # a feature of this project, not a bug.
    while len(history) > 1 and _estimated_tokens(history) > CTX_SIZE:
        history.pop(1)
    return history


async def _send(websocket, payload):
    await websocket.send(json.dumps(payload))


async def _run_inference(websocket, prompt):
    await _send(websocket, {"state": "THINKING", "type": "state"})

    history.append({"role": "user", "content": prompt})

    speech_id = os.urandom(8).hex()
    thinking_open = False
    speaking = False
    reply = ""

    headers = {}
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"

    # Inference may take a geological amount of time.
    timeout = httpx.Timeout(None, connect=30)

    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream(
            "POST",
            f"{API_URL}/chat/completions",
            headers=headers,
            json={
                "model": MODEL,
                "messages": _fit_context(),
                "stream": True
            }
        ) as response:
            response.raise_for_status()

            async for line in response.aiter_lines():
                line = line.strip()

                if not line.startswith("data:"):
                    continue

                data = line[5:].strip()

                if data == "[DONE]":
                    break

                payload = json.loads(data)
                choices = payload.get("choices")

                if not choices:
                    continue

                delta = choices[0].get("delta") or {}
                # llama.cpp's server uses "reasoning"; others "reasoning_content".
                reasoning = delta.get("reasoning") or delta.get("reasoning_content")
                content = delta.get("content")

                if reasoning:
                    if not thinking_open:
                        await _send(websocket, {"content": START_THINKING, "type": "trace"})
                        thinking_open = True
                    await _send(websocket, {"content": reasoning, "type": "trace"})

                if content:
                    if thinking_open:
                        await _send(websocket, {"content": END_THINKING, "type": "trace"})
                        thinking_open = False

                    if not speaking:
                        await _send(websocket, {"state": "SPEAKING", "type": "state"})
                        await _send(websocket, {"speech_id": speech_id, "type": "speech_start"})
                        speaking = True

                    reply += content
                    await _send(
                        websocket,
                        {"content": content, "speech_id": speech_id, "type": "speech_chunk"}
                    )

    if thinking_open:
        await _send(websocket, {"content": END_THINKING, "type": "trace"})

    if speaking:
        await _send(websocket, {"speech_id": speech_id, "type": "speech_end"})

    if reply:
        history.append({"role": "assistant", "content": reply})

    await _send(websocket, {"state": "IDLE", "type": "state"})


async def main():
    websocket = None

    # The moderator (or the network) may not be up yet. A few patient
    # retries keep the logs sane; restart: unless-stopped is the backup.
    for attempt in range(1, 11):
        try:
            websocket = await websockets.connect(MODERATOR)
            break
        except OSError:
            if attempt == 10:
                raise
            print(f"Moderator unreachable at {MODERATOR}, retry {attempt}/10...", flush=True)
            await asyncio.sleep(2)

    async with websocket:
        await websocket.send(
            json.dumps(
                {
                    "name": NAME,
                    "personality": PERSONALITY,
                    "type": "connect"
                }
            )
        )

        acknowledgement = json.loads(await websocket.recv())

        if acknowledgement.get("type") != "connected":
            raise RuntimeError(acknowledgement)

        print(
            f'{acknowledgement["name"]} connected '
            f'({acknowledgement["connection_id"]}) '
            f'(speak to {API_URL}, model {MODEL})',
            flush=True
        )

        async for raw_message in websocket:
            message = json.loads(raw_message)

            if message.get("type") == "prompt":
                await _run_inference(websocket, message["prompt"])


if __name__ == "__main__":
    asyncio.run(main())
