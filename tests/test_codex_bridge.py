import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

import codex_bridge  # noqa: E402


def parse_events(blocks):
    events = []
    for block in blocks:
        text = block.decode()
        for line in text.split("\n"):
            if line.startswith("data:"):
                events.append(json.loads(line[5:].strip()))
    return events


class RequestConversionTest(unittest.TestCase):
    def test_instructions_become_a_system_message(self):
        body, _, _ = codex_bridge.responses_to_chat(
            {"instructions": "be terse", "input": [
                {"type": "message", "role": "user",
                 "content": [{"type": "input_text", "text": "hi"}]}
            ]}, "qwen3.7-max")
        self.assertEqual(body["messages"][0], {"role": "system", "content": "be terse"})
        self.assertEqual(body["messages"][1], {"role": "user", "content": "hi"})
        self.assertEqual(body["model"], "qwen3.7-max")
        self.assertEqual(body["stream_options"], {"include_usage": True})

    def test_function_call_and_output_pair_into_chat_shape(self):
        body, _, _ = codex_bridge.responses_to_chat({"input": [
            {"type": "function_call", "call_id": "c1", "name": "shell",
             "arguments": "{\"cmd\":\"ls\"}"},
            {"type": "function_call_output", "call_id": "c1", "output": "a.txt"},
        ]}, "m")
        assistant, tool = body["messages"]
        self.assertEqual(assistant["role"], "assistant")
        self.assertEqual(assistant["tool_calls"][0]["id"], "c1")
        self.assertEqual(assistant["tool_calls"][0]["function"]["name"], "shell")
        self.assertEqual(tool, {"role": "tool", "tool_call_id": "c1", "content": "a.txt"})

    def test_parallel_calls_merge_into_one_assistant_message(self):
        body, _, _ = codex_bridge.responses_to_chat({"input": [
            {"type": "function_call", "call_id": "c1", "name": "a", "arguments": "{}"},
            {"type": "function_call", "call_id": "c2", "name": "b", "arguments": "{}"},
            {"type": "function_call_output", "call_id": "c1", "output": "1"},
            {"type": "function_call_output", "call_id": "c2", "output": "2"},
        ]}, "m")
        self.assertEqual(len(body["messages"]), 3)
        self.assertEqual(len(body["messages"][0]["tool_calls"]), 2)

    def test_structured_function_output_is_flattened(self):
        body, _, _ = codex_bridge.responses_to_chat({"input": [
            {"type": "function_call_output", "call_id": "c1", "output": {"output": "done"}},
        ]}, "m")
        self.assertEqual(body["messages"][0]["content"], "done")

    def test_reasoning_items_are_not_replayed_upstream(self):
        body, _, _ = codex_bridge.responses_to_chat({"input": [
            {"type": "reasoning", "summary": [{"type": "summary_text", "text": "think"}]},
            {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "go"}]},
        ]}, "m")
        self.assertEqual([m["role"] for m in body["messages"]], ["user"])

    def test_custom_tool_becomes_a_string_input_function(self):
        body, custom, dropped = codex_bridge.responses_to_chat({
            "tools": [
                {"type": "custom", "name": "apply_patch", "description": "patch"},
                {"type": "function", "name": "shell", "parameters": {"type": "object"}},
                {"type": "web_search"},
            ],
            "input": [],
        }, "m")
        self.assertEqual(custom, {"apply_patch"})
        self.assertEqual(dropped, ["web_search"])
        names = [t["function"]["name"] for t in body["tools"]]
        self.assertEqual(names, ["apply_patch", "shell"])
        patch_params = body["tools"][0]["function"]["parameters"]
        self.assertEqual(patch_params["required"], ["input"])

    def test_images_survive_as_multipart_content(self):
        body, _, _ = codex_bridge.responses_to_chat({"input": [
            {"type": "message", "role": "user", "content": [
                {"type": "input_text", "text": "what is this"},
                {"type": "input_image", "image_url": "data:image/png;base64,AAAA"},
            ]},
        ]}, "m")
        parts = body["messages"][0]["content"]
        self.assertEqual(parts[0]["type"], "text")
        self.assertEqual(parts[1]["image_url"]["url"], "data:image/png;base64,AAAA")

    def test_max_output_tokens_maps_to_max_tokens(self):
        body, _, _ = codex_bridge.responses_to_chat(
            {"input": [], "max_output_tokens": 256, "temperature": 0.2}, "m")
        self.assertEqual(body["max_tokens"], 256)
        self.assertEqual(body["temperature"], 0.2)

    def test_extra_body_is_merged_last(self):
        body, _, _ = codex_bridge.responses_to_chat(
            {"input": []}, "m", {"enable_thinking": False})
        self.assertIs(body["enable_thinking"], False)


class StreamConversionTest(unittest.TestCase):
    def test_text_stream_produces_added_delta_done_completed(self):
        state = codex_bridge.ResponsesStream("m")
        events = parse_events(state.start())
        events += parse_events(state.feed({"choices": [{"delta": {"content": "Hel"}}]}))
        events += parse_events(state.feed({"choices": [{"delta": {"content": "lo"}}]}))
        events += parse_events(state.finish())

        types = [e["type"] for e in events]
        self.assertEqual(types, [
            "response.created",
            "response.output_item.added",
            "response.output_text.delta",
            "response.output_text.delta",
            "response.output_item.done",
            "response.completed",
        ])
        done = events[-2]["item"]
        self.assertEqual(done["content"][0]["text"], "Hello")
        self.assertEqual(done["role"], "assistant")
        self.assertEqual(events[-1]["response"]["status"], "completed")
        self.assertEqual([e["sequence_number"] for e in events], list(range(1, 7)))

    def test_reasoning_content_becomes_a_reasoning_item(self):
        state = codex_bridge.ResponsesStream("m")
        state.start()
        events = parse_events(state.feed(
            {"choices": [{"delta": {"reasoning_content": "step one"}}]}))
        events += parse_events(state.finish())
        types = [e["type"] for e in events]
        self.assertIn("response.reasoning_summary_text.delta", types)
        item = next(e["item"] for e in events
                    if e["type"] == "response.output_item.done")
        self.assertEqual(item["type"], "reasoning")
        self.assertEqual(item["summary"][0]["text"], "step one")

    def test_tool_call_fragments_accumulate_into_one_function_call(self):
        state = codex_bridge.ResponsesStream("m")
        state.start()
        state.feed({"choices": [{"delta": {"tool_calls": [
            {"index": 0, "id": "call_1", "function": {"name": "shell", "arguments": "{\"cmd\""}}]}}]})
        state.feed({"choices": [{"delta": {"tool_calls": [
            {"index": 0, "function": {"arguments": ":\"ls\"}"}}]}}]})
        events = parse_events(state.finish())
        item = events[0]["item"]
        self.assertEqual(item["type"], "function_call")
        self.assertEqual(item["call_id"], "call_1")
        self.assertEqual(json.loads(item["arguments"]), {"cmd": "ls"})

    def test_custom_tool_call_is_mapped_back_to_freeform_input(self):
        state = codex_bridge.ResponsesStream("m", {"apply_patch"})
        state.start()
        state.feed({"choices": [{"delta": {"tool_calls": [
            {"index": 0, "id": "c9", "function": {
                "name": "apply_patch",
                "arguments": json.dumps({"input": "*** Begin Patch"})}}]}}]})
        item = parse_events(state.finish())[0]["item"]
        self.assertEqual(item["type"], "custom_tool_call")
        self.assertEqual(item["input"], "*** Begin Patch")
        self.assertEqual(item["call_id"], "c9")

    def test_usage_is_translated_to_responses_shape(self):
        state = codex_bridge.ResponsesStream("m")
        state.start()
        state.feed({"choices": [], "usage": {
            "prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 14,
            "prompt_tokens_details": {"cached_tokens": 6},
            "completion_tokens_details": {"reasoning_tokens": 2}}})
        completed = parse_events(state.finish())[-1]
        self.assertEqual(completed["response"]["usage"], {
            "input_tokens": 10,
            "input_tokens_details": {"cached_tokens": 6},
            "output_tokens": 4,
            "output_tokens_details": {"reasoning_tokens": 2},
            "total_tokens": 14,
        })

    def test_failure_emits_response_failed_once(self):
        state = codex_bridge.ResponsesStream("m")
        state.start()
        events = parse_events(state.fail("quota exceeded"))
        self.assertEqual(events[0]["type"], "response.failed")
        self.assertEqual(events[0]["response"]["error"]["message"], "quota exceeded")
        self.assertEqual(state.finish(), [])

    def test_non_streaming_body_becomes_a_completed_response(self):
        state = codex_bridge.chat_response_to_stream({
            "choices": [{"message": {"content": "hi", "tool_calls": [
                {"id": "c1", "function": {"name": "shell", "arguments": "{}"}}]}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 2},
        }, "m")
        snapshot = state.snapshot()
        kinds = [item["type"] for item in snapshot["output"]]
        self.assertEqual(kinds, ["message", "function_call"])
        self.assertEqual(snapshot["usage"]["total_tokens"], 3)


class SseParsingTest(unittest.TestCase):
    def test_frames_split_across_reads_are_reassembled(self):
        blocks = [b"data: {\"a\":", b"1}\n\ndata: [DONE]\n\n", b""]
        reader = iter(blocks).__next__
        self.assertEqual(list(codex_bridge.iter_sse_data(reader)), ['{"a":1}', "[DONE]"])

    def test_trailing_frame_without_blank_line_is_still_yielded(self):
        blocks = [b"data: {\"a\":1}", b""]
        reader = iter(blocks).__next__
        self.assertEqual(list(codex_bridge.iter_sse_data(reader)), ['{"a":1}'])


if __name__ == "__main__":
    unittest.main()
