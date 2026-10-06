# idiot-client-server

A D.I.P.S.H.I.T. idiot whose thinking is farmed out to an OpenAI-compatible
inference server (llama.cpp `llama-server`, Ollama, vLLM, ...) instead of
keeping a `llama-cli` subprocess in its gut.

The sibling in `../idiot` is untouched. The moderator protocol — connect
handshake, `prompt` in, `state` / `trace` / `speech_*` out — is identical,
so the moderator, nginx, and the web UI need no changes. Reasoning deltas
are translated back into the literal `[Start thinking]` / `[End thinking]`
markers the UI colors on.

Because the OpenAI API is stateless, this client keeps the conversation
history itself and truncates the oldest events when the rough token count
exceeds `DIPSHIT_CTX_SIZE`. Forgetting is a feature.

## Environment

| Variable | Default | Meaning |
|---|---|---|
| `DIPSHIT_MODERATOR` | `ws://moderator:8000/ws/idiot` | Moderator WebSocket |
| `DIPSHIT_API_URL` | `http://llama:8081` | OpenAI-compatible server base URL |
| `DIPSHIT_API_KEY` | _(empty)_ | Sent as `Authorization: Bearer` if set |
| `DIPSHIT_MODEL` | `Qwen3-1.7B-Q4_K_M` | Model id for the server |
| `DIPSHIT_NAME` | hostname | Idiot name |
| `DIPSHIT_CTX_SIZE` | `4096` | Rough token budget before old events are forgotten |
| `DIPSHIT_CURIOSITY` / `DIPSHIT_FRIENDLINESS` / `DIPSHIT_SOCIABILITY` | `75` / `50` / `25` | Personality seed, 1–100 |

## Run

```bash
pip install -r requirements.txt
DIPSHIT_MODERATOR=ws://localhost:8000/ws/idiot \
DIPSHIT_API_URL=http://localhost:8081 \
python idiot.py
```

Or via the compose file, where `marvin` is a ready-made example wired to an
OpenAI-compatible server on the host.
