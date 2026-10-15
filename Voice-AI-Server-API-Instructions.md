# Voice AI API Instructions

Use this guide to integrate an application, browser, mobile device, or ESP32 with the Voice AI Server.

## Connection

- Base URL: `http://SERVER_IP:8000`
- Local example: `http://127.0.0.1:8000`
- Interactive OpenAPI documentation: `http://SERVER_IP:8000/docs`
- All endpoints except `GET /healthz` require a bearer token when the server's `API_KEY` setting is non-empty.

```http
Authorization: Bearer <API_KEY>
```

For production or any untrusted network, put the API behind HTTPS, set `API_KEY`, and restrict CORS origins.

## Quick start

Confirm that the HTTP server is reachable:

```bash
curl http://127.0.0.1:8000/healthz
```

Expected response:

```json
{"status":"ok"}
```

This checks HTTP availability only. It does not prove that Ollama, Qdrant, Whisper, or the TTS backend is ready.

## Endpoints

| Method and path | Content type | Returns | Use |
| --- | --- | --- | --- |
| `GET /healthz` | None | JSON | Check HTTP availability |
| `POST /v1/chat/completions` | `application/json` | JSON or SSE | Text chat with RAG knowledge |
| `POST /v1/images/chat` | `multipart/form-data` | JSON | Ask a vision model about an image |
| `POST /v1/audio/transcriptions` | `multipart/form-data` | JSON | Transcribe audio |
| `POST /v1/audio/speech` | `application/json` | WAV bytes | Synthesize speech |
| `POST /v1/voice/chat` | `multipart/form-data` | WAV bytes or JSON | Run the full voice-assistant pipeline |

## Text chat

`POST /v1/chat/completions`

The server retrieves relevant knowledge for the last user message, adds it to the model context, and returns an assistant answer.

Request fields:

| Field | Required | Description |
| --- | --- | --- |
| `messages` | Yes | Array of 1-30 `{role, content}` objects |
| `messages[].role` | Yes | `system`, `user`, or `assistant` |
| `messages[].content` | Yes | String message content |
| `model` | No | Ollama model override |
| `stream` | No | Boolean; defaults to `false` |

Non-streaming example:

```bash
curl http://127.0.0.1:8000/v1/chat/completions \
  -H 'Authorization: Bearer <API_KEY>' \
  -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"What are my ESP32 projects?"}]}'
```

Response:

```json
{
  "choices": [
    {
      "message": {
        "role": "assistant",
        "content": "..."
      }
    }
  ]
}
```

Streaming example:

```bash
curl -N http://127.0.0.1:8000/v1/chat/completions \
  -H 'Authorization: Bearer <API_KEY>' \
  -H 'Content-Type: application/json' \
  -d '{"stream":true,"messages":[{"role":"user","content":"Give me a short summary."}]}'
```

The response uses `text/event-stream`. Each event contains a JSON delta and the stream ends with `[DONE]`:

```text
data: {"delta":"partial text"}

data: [DONE]
```

If streaming fails after it starts, the server emits `data: {"error":"..."}` instead of changing the HTTP status.

## Image chat

`POST /v1/images/chat`

Upload one JPEG, PNG, or WebP image. The default maximum size is 10 MB. Use a vision-capable Ollama model such as `gemma3:4b`; Home Assistant tools are disabled on this endpoint.

| Form field | Required | Description |
| --- | --- | --- |
| `image` | Yes | JPEG, PNG, or WebP file |
| `prompt` | Yes | Question containing 1-10,000 characters |
| `model` | No | Vision-model override |

```bash
curl http://127.0.0.1:8000/v1/images/chat \
  -H 'Authorization: Bearer <API_KEY>' \
  -F 'image=@camera.jpg;type=image/jpeg' \
  -F 'prompt=What is in this image?' \
  -F 'model=gemma3:4b'
```

The response has the same `choices[0].message.content` shape as non-streaming text chat.

## Speech-to-text

`POST /v1/audio/transcriptions`

| Form field | Required | Description |
| --- | --- | --- |
| `audio` | Yes | Audio file; default limit is 25 MB |
| `language` | No | Whisper language code such as `en` or `vi`; omit for detection |

```bash
curl http://127.0.0.1:8000/v1/audio/transcriptions \
  -H 'Authorization: Bearer <API_KEY>' \
  -F 'audio=@question.wav' \
  -F 'language=en'
```

Response:

```json
{"text":"How are you?","language":"en"}
```

Supported input includes WAV, MP3, M4A, WebM, and other formats understood by the audio backend. For ESP32 clients, prefer mono 16-bit PCM WAV at 16 kHz or 24 kHz.

## Text-to-speech

`POST /v1/audio/speech`

| JSON field | Required | Description |
| --- | --- | --- |
| `text` | Yes | Text containing 1-10,000 characters |
| `language` | No | Enabled TTS language, normally `en`, `ja`, or a configured `vi` backend |
| `voice` | No | Voice override compatible with the selected language |
| `speed` | No | Number from `0.5` to `2.0`; defaults to `1.0` |

```bash
curl http://127.0.0.1:8000/v1/audio/speech \
  -H 'Authorization: Bearer <API_KEY>' \
  -H 'Content-Type: application/json' \
  -d '{"text":"Hello.","language":"en","voice":"af_heart","speed":1.0}' \
  --output reply.wav
```

The response is binary `audio/wav`, 16-bit PCM at 24 kHz. The Vietnamese backend currently ignores `speed`.

## Complete voice chat

`POST /v1/voice/chat`

This route runs `audio -> transcription -> session history -> RAG -> Ollama -> speech synthesis`.

| Form field | Required | Default | Description |
| --- | --- | --- | --- |
| `audio` | Yes | None | Recorded speech |
| `session_id` | No | `default` | Conversation identifier; use one per user or device |
| `language` | No | Auto-detect | Selects STT and response TTS language |
| `voice` | No | Server default | TTS voice override |
| `model` | No | Server default | Ollama model override |
| `response_format` | No | `audio` | `audio` or `json` |

Binary response, recommended for ESP32:

```bash
curl http://192.168.1.10:8000/v1/voice/chat \
  -H 'Authorization: Bearer <API_KEY>' \
  -F 'audio=@question.wav' \
  -F 'session_id=esp32-kitchen' \
  -F 'language=en' \
  --output answer.wav
```

The response has `Content-Type: audio/wav`. Read it as bytes, not as a string. Useful headers include `X-Transcript-Length`, `X-Response-Text-Length`, and `Content-Disposition`.

JSON response, useful for debugging and web interfaces:

```bash
curl http://127.0.0.1:8000/v1/voice/chat \
  -H 'Authorization: Bearer <API_KEY>' \
  -F 'audio=@question.wav' \
  -F 'session_id=browser-001' \
  -F 'response_format=json'
```

```json
{
  "transcript": "Recognized speech",
  "language": "en",
  "text": "Assistant response",
  "audio_format": "wav",
  "audio_base64": "UklGRi..."
}
```

Base64 audio is approximately 33% larger than the binary WAV. Prefer binary mode unless the client needs text and audio in one response.

## Browser examples

Text chat:

```javascript
const response = await fetch(`${baseUrl}/v1/chat/completions`, {
  method: "POST",
  headers: {
    "Authorization": `Bearer ${apiKey}`,
    "Content-Type": "application/json",
  },
  body: JSON.stringify({
    messages: [{ role: "user", content: "What can you help me with?" }],
  }),
});

if (!response.ok) throw new Error(await response.text());
const data = await response.json();
console.log(data.choices[0].message.content);
```

Voice chat with a binary response:

```javascript
const form = new FormData();
form.append("audio", audioBlob, "question.wav");
form.append("session_id", "browser-001");
form.append("response_format", "audio");

const response = await fetch(`${baseUrl}/v1/voice/chat`, {
  method: "POST",
  headers: { "Authorization": `Bearer ${apiKey}` },
  body: form,
});

if (!response.ok) throw new Error(await response.text());
const wav = await response.blob();
new Audio(URL.createObjectURL(wav)).play();
```

Do not manually set `Content-Type` for `FormData`; the browser must add the multipart boundary.

## Errors

FastAPI errors normally use this JSON shape:

```json
{"detail":"Error description"}
```

| Status | Meaning |
| --- | --- |
| `401` | Bearer token is missing or invalid |
| `413` | Uploaded audio/image is empty or exceeds its configured size limit |
| `422` | Request validation failed, the media could not be processed, or a field is invalid |
| `503` | Ollama, Qdrant/RAG, Whisper, or TTS failed or is unavailable |

Always check the HTTP status before parsing a success response. Client timeouts should exceed the server's Ollama timeout and allow additional time for transcription and speech synthesis. Voice responses are generated completely before delivery; audio streaming is not implemented.

## Client integration rules

- Keep `API_KEY` outside source control. Never embed a privileged production key in public browser code or firmware.
- Give each device or user a stable, distinct `session_id` to prevent conversation histories from mixing.
- Use multipart field names exactly as documented. Audio uploads must use `audio`; image uploads must use `image`.
- Use JSON text chat when speech is unnecessary; it avoids loading or invoking Whisper and TTS.
- Use binary voice responses on memory-constrained clients.
- Retry transient `503` and network failures with bounded exponential backoff. Do not automatically retry validation errors.
- The server may allow selected Home Assistant actions during chat or voice requests. Treat API access as permission to request those allowlisted physical actions.
