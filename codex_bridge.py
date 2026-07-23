"""Translate between the OpenAI Responses API and OpenAI Chat Completions.

Codex CLI 0.122+ removed `wire_api = "chat"`, so a custom provider must speak the
Responses API. Most third-party providers (including Alibaba Model Studio's
`/compatible-mode/v1`) only speak Chat Completions. This module is the missing
adapter:

    Codex --/v1/responses--> claudecodex --/chat/completions--> provider

Pure functions plus one small streaming state machine. Standard library only, no
network calls, so every rule here is unit testable offline.
"""
import json
import time
import uuid

TEXT_PART_TYPES = ("input_text", "output_text", "text", "summary_text")


def new_id(prefix):
    return f"{prefix}_{uuid.uuid4().hex}"


# --------------------------------------------------------------------------
# Responses request  ->  Chat Completions request
# --------------------------------------------------------------------------

def _part_text(part):
    if isinstance(part, str):
        return part
    if isinstance(part, dict) and part.get("type") in TEXT_PART_TYPES:
        return part.get("text") or ""
    return ""


def content_to_text(content):
    """Flatten a Responses content value to plain text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(_part_text(p) for p in content)
    return ""


def _image_parts(content):
    out = []
    if isinstance(content, list):
        for part in content:
            if isinstance(part, dict) and part.get("type") == "input_image":
                url = part.get("image_url")
                if isinstance(url, dict):
                    url = url.get("url")
                if url:
                    out.append({"type": "image_url", "image_url": {"url": url}})
    return out


def _chat_content(content):
    """Return either a plain string or an OpenAI multipart content list."""
    images = _image_parts(content)
    text = content_to_text(content)
    if not images:
        return text
    parts = []
    if text:
        parts.append({"type": "text", "text": text})
    parts.extend(images)
    return parts


def _output_to_text(output):
    """`function_call_output.output` is a string, an object, or content parts."""
    if isinstance(output, str):
        return output
    if isinstance(output, dict):
        if "output" in output:
            return _output_to_text(output["output"])
        if "content" in output:
            return content_to_text(output["content"])
        return json.dumps(output, ensure_ascii=False)
    if isinstance(output, list):
        return content_to_text(output)
    return "" if output is None else str(output)


def convert_tools(tools):
    """Responses tools -> Chat tools.

    Returns (chat_tools, custom_names). Freeform `custom` tools (Codex uses one
    for apply_patch) have no Chat equivalent, so they become a function with a
    single string `input` property and are converted back on the way out.
    Provider-side tools Codex cannot delegate to us (web_search, local_shell,
    image_generation) are dropped: Codex still has the shell function tool.
    """
    chat_tools = []
    custom_names = set()
    dropped = []
    for tool in tools or []:
        if not isinstance(tool, dict):
            continue
        kind = tool.get("type")
        if kind == "function":
            spec = tool.get("function") if isinstance(tool.get("function"), dict) else tool
            name = spec.get("name")
            if not name:
                continue
            chat_tools.append({
                "type": "function",
                "function": {
                    "name": name,
                    "description": spec.get("description") or "",
                    "parameters": spec.get("parameters") or {"type": "object", "properties": {}},
                },
            })
        elif kind == "custom":
            name = tool.get("name")
            if not name:
                continue
            custom_names.add(name)
            chat_tools.append({
                "type": "function",
                "function": {
                    "name": name,
                    "description": tool.get("description") or "",
                    "parameters": {
                        "type": "object",
                        "properties": {"input": {"type": "string"}},
                        "required": ["input"],
                    },
                },
            })
        else:
            dropped.append(kind)
    return chat_tools, custom_names, dropped


def _flush_calls(messages, calls):
    if calls:
        messages.append({"role": "assistant", "content": None, "tool_calls": list(calls)})
        calls.clear()


def convert_input(items, custom_names):
    """Responses `input` items -> Chat `messages`."""
    messages = []
    calls = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        kind = item.get("type") or "message"

        if kind == "function_call":
            calls.append({
                "id": item.get("call_id") or item.get("id") or new_id("call"),
                "type": "function",
                "function": {
                    "name": item.get("name") or "",
                    "arguments": item.get("arguments") or "{}",
                },
            })
            continue

        if kind == "custom_tool_call":
            name = item.get("name") or ""
            custom_names.add(name)
            calls.append({
                "id": item.get("call_id") or item.get("id") or new_id("call"),
                "type": "function",
                "function": {
                    "name": name,
                    "arguments": json.dumps({"input": item.get("input") or ""}, ensure_ascii=False),
                },
            })
            continue

        _flush_calls(messages, calls)

        if kind in ("function_call_output", "custom_tool_call_output"):
            messages.append({
                "role": "tool",
                "tool_call_id": item.get("call_id") or item.get("id") or "",
                "content": _output_to_text(item.get("output")),
            })
            continue

        if kind == "reasoning":
            # Upstream reasoning state is not portable across providers.
            continue

        if kind == "message":
            role = item.get("role") or "user"
            if role == "developer":
                role = "system"
            content = _chat_content(item.get("content"))
            if content == "" or content == []:
                continue
            messages.append({"role": role, "content": content})
            continue

        # Unknown item type: keep whatever text it carries rather than lose turn context.
        text = content_to_text(item.get("content"))
        if text:
            messages.append({"role": "user", "content": text})

    _flush_calls(messages, calls)
    return messages


def responses_to_chat(req, model, extra_body=None):
    """Build a Chat Completions request body from a Responses request body."""
    chat_tools, custom_names, dropped = convert_tools(req.get("tools"))
    messages = []
    instructions = req.get("instructions")
    if instructions:
        messages.append({"role": "system", "content": instructions})
    messages.extend(convert_input(req.get("input"), custom_names))

    body = {
        "model": model,
        "messages": messages,
        "stream": bool(req.get("stream", True)),
    }
    if body["stream"]:
        body["stream_options"] = {"include_usage": True}
    if chat_tools:
        body["tools"] = chat_tools
        choice = req.get("tool_choice")
        if choice in ("auto", "none", "required"):
            body["tool_choice"] = choice
        elif isinstance(choice, dict) and choice.get("name"):
            body["tool_choice"] = {"type": "function", "function": {"name": choice["name"]}}
        if req.get("parallel_tool_calls") is not None:
            body["parallel_tool_calls"] = bool(req["parallel_tool_calls"])
    for src, dst in (("max_output_tokens", "max_tokens"), ("temperature", "temperature"),
                     ("top_p", "top_p")):
        if req.get(src) is not None:
            body[dst] = req[src]
    if isinstance(extra_body, dict):
        body.update(extra_body)
    return body, custom_names, dropped


# --------------------------------------------------------------------------
# Chat Completions stream  ->  Responses stream
# --------------------------------------------------------------------------

def sse(event):
    return f"event: {event['type']}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n".encode()


class ResponsesStream:
    """Accumulate Chat Completions chunks and emit Responses SSE events.

    Codex needs `response.output_item.done` for every produced item and a final
    `response.completed`; the deltas in between are what makes output appear
    live instead of in one block at the end.
    """

    def __init__(self, model, custom_names=(), response_id=None):
        self.model = model
        self.custom_names = set(custom_names)
        self.response_id = response_id or new_id("resp")
        self.seq = 0
        self.created_at = int(time.time())
        self.output = []          # finished items, in emission order
        self.next_index = 0
        self.text = ""
        self.text_item_id = None
        self.text_index = None
        self.reasoning = ""
        self.reasoning_item_id = None
        self.reasoning_index = None
        self.calls = {}           # chat tool_call index -> accumulator
        self.usage = None
        self.finished = False

    # -- helpers ---------------------------------------------------------
    def _event(self, payload):
        self.seq += 1
        payload["sequence_number"] = self.seq
        return sse(payload)

    def _envelope(self, status, output=None):
        env = {
            "id": self.response_id,
            "object": "response",
            "created_at": self.created_at,
            "status": status,
            "model": self.model,
            "output": output if output is not None else [],
        }
        if self.usage is not None:
            env["usage"] = self.usage
        return env

    def _take_index(self):
        index = self.next_index
        self.next_index += 1
        return index

    # -- stream lifecycle ------------------------------------------------
    def start(self):
        return [self._event({"type": "response.created", "response": self._envelope("in_progress")})]

    def _ensure_reasoning(self, out):
        if self.reasoning_item_id is None:
            self.reasoning_item_id = new_id("rs")
            self.reasoning_index = self._take_index()
            out.append(self._event({
                "type": "response.output_item.added",
                "output_index": self.reasoning_index,
                "item": {"type": "reasoning", "id": self.reasoning_item_id,
                         "summary": [], "content": []},
            }))

    def _ensure_text(self, out):
        if self.text_item_id is None:
            self.text_item_id = new_id("msg")
            self.text_index = self._take_index()
            out.append(self._event({
                "type": "response.output_item.added",
                "output_index": self.text_index,
                "item": {"type": "message", "id": self.text_item_id, "status": "in_progress",
                         "role": "assistant", "content": []},
            }))

    def feed(self, chunk):
        """Consume one parsed Chat Completions SSE chunk. Returns SSE bytes."""
        out = []
        if not isinstance(chunk, dict):
            return out

        usage = chunk.get("usage")
        if isinstance(usage, dict):
            self.usage = normalize_usage(usage)

        for choice in chunk.get("choices") or []:
            delta = choice.get("delta") or {}

            reasoning = delta.get("reasoning_content") or delta.get("reasoning")
            if isinstance(reasoning, str) and reasoning:
                self._ensure_reasoning(out)
                self.reasoning += reasoning
                out.append(self._event({
                    "type": "response.reasoning_summary_text.delta",
                    "item_id": self.reasoning_item_id,
                    "output_index": self.reasoning_index,
                    "summary_index": 0,
                    "delta": reasoning,
                }))

            text = delta.get("content")
            if isinstance(text, list):
                text = content_to_text(text)
            if isinstance(text, str) and text:
                self._ensure_text(out)
                self.text += text
                out.append(self._event({
                    "type": "response.output_text.delta",
                    "item_id": self.text_item_id,
                    "output_index": self.text_index,
                    "content_index": 0,
                    "delta": text,
                }))

            for call in delta.get("tool_calls") or []:
                if not isinstance(call, dict):
                    continue
                key = call.get("index")
                if key is None:
                    key = call.get("id") or len(self.calls)
                acc = self.calls.setdefault(key, {"id": None, "name": "", "arguments": ""})
                if call.get("id"):
                    acc["id"] = call["id"]
                fn = call.get("function") or {}
                if fn.get("name"):
                    acc["name"] = fn["name"]
                if fn.get("arguments"):
                    acc["arguments"] += fn["arguments"]
        return out

    def _close_reasoning(self, out):
        if self.reasoning_item_id is None:
            return
        item = {"type": "reasoning", "id": self.reasoning_item_id,
                "summary": [{"type": "summary_text", "text": self.reasoning}] if self.reasoning else [],
                "content": []}
        self.output.append(item)
        out.append(self._event({"type": "response.output_item.done",
                                "output_index": self.reasoning_index, "item": item}))

    def _close_text(self, out):
        if self.text_item_id is None:
            return
        item = {"type": "message", "id": self.text_item_id, "status": "completed",
                "role": "assistant",
                "content": [{"type": "output_text", "text": self.text, "annotations": []}]}
        self.output.append(item)
        out.append(self._event({"type": "response.output_item.done",
                                "output_index": self.text_index, "item": item}))

    def _close_calls(self, out):
        for key in sorted(self.calls, key=lambda k: (isinstance(k, str), k)):
            acc = self.calls[key]
            if not acc["name"]:
                continue
            call_id = acc["id"] or new_id("call")
            index = self._take_index()
            if acc["name"] in self.custom_names:
                item = {"type": "custom_tool_call", "id": new_id("ctc"), "call_id": call_id,
                        "name": acc["name"], "input": _custom_input(acc["arguments"]),
                        "status": "completed"}
            else:
                item = {"type": "function_call", "id": new_id("fc"), "call_id": call_id,
                        "name": acc["name"], "arguments": acc["arguments"] or "{}",
                        "status": "completed"}
            self.output.append(item)
            out.append(self._event({"type": "response.output_item.done",
                                    "output_index": index, "item": item}))

    def finish(self):
        if self.finished:
            return []
        self.finished = True
        out = []
        self._close_reasoning(out)
        self._close_text(out)
        self._close_calls(out)
        out.append(self._event({"type": "response.completed",
                                "response": self._envelope("completed", self.output)}))
        return out

    def fail(self, message, code=None):
        if self.finished:
            return []
        self.finished = True
        env = self._envelope("failed", self.output)
        env["error"] = {"code": code or "upstream_error", "message": message}
        return [self._event({"type": "response.failed", "response": env})]

    def snapshot(self):
        """Non-streaming Responses body, for `stream: false` requests."""
        if not self.finished:
            self.finish()
        return self._envelope("completed", self.output)


def _custom_input(arguments):
    try:
        parsed = json.loads(arguments or "{}")
    except (TypeError, ValueError):
        return arguments or ""
    if isinstance(parsed, dict) and "input" in parsed:
        value = parsed["input"]
        return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return arguments or ""


def normalize_usage(usage):
    prompt = usage.get("prompt_tokens") or usage.get("input_tokens") or 0
    completion = usage.get("completion_tokens") or usage.get("output_tokens") or 0
    details = usage.get("prompt_tokens_details") or {}
    out_details = usage.get("completion_tokens_details") or {}
    return {
        "input_tokens": prompt,
        "input_tokens_details": {"cached_tokens": details.get("cached_tokens") or 0},
        "output_tokens": completion,
        "output_tokens_details": {"reasoning_tokens": out_details.get("reasoning_tokens") or 0},
        "total_tokens": usage.get("total_tokens") or (prompt + completion),
    }


def chat_response_to_stream(payload, model, custom_names=()):
    """Adapt a non-streaming Chat Completions body into a finished stream state."""
    state = ResponsesStream(model, custom_names)
    choices = payload.get("choices") or []
    chunk = {"choices": [], "usage": payload.get("usage")}
    for choice in choices:
        message = choice.get("message") or {}
        chunk["choices"].append({"delta": {
            "content": message.get("content"),
            "reasoning_content": message.get("reasoning_content"),
            "tool_calls": [
                {"index": i, "id": c.get("id"), "function": c.get("function")}
                for i, c in enumerate(message.get("tool_calls") or [])
            ],
        }})
    state.feed(chunk)
    return state


def iter_sse_data(chunk_reader):
    """Yield `data:` payload strings from an SSE byte stream.

    `chunk_reader` is a callable returning the next bytes block, or b"" at EOF.
    """
    buffer = b""
    while True:
        block = chunk_reader()
        if not block:
            break
        buffer += block
        while b"\n\n" in buffer:
            frame, buffer = buffer.split(b"\n\n", 1)
            for line in frame.split(b"\n"):
                if line.startswith(b"data:"):
                    yield line[5:].strip().decode("utf-8", "replace")
    for line in buffer.split(b"\n"):
        if line.startswith(b"data:"):
            yield line[5:].strip().decode("utf-8", "replace")
