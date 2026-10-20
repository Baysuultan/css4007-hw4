import copy
import json
from types import SimpleNamespace

from strategies import MAX_TOOL_ROUNDS, StrategyRunner


class FakeMessage:
    def __init__(self, content=None, tool_calls=None, wire_message=None):
        self.content = content
        self.tool_calls = tool_calls
        self.wire_message = wire_message or {"role": "assistant", "content": content}

    def model_dump(self, exclude_none=True):
        return copy.deepcopy(self.wire_message)


class FakeCompletions:
    def __init__(self, responses):
        self.responses = responses
        self.requests = []

    def create(self, **kwargs):
        self.requests.append(copy.deepcopy(kwargs))
        return self.responses.pop(0)


def make_response(message):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=message)],
        usage=SimpleNamespace(prompt_tokens=12, completion_tokens=3),
    )


def fake_tool_call(call_id="call-1"):
    request_message = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": call_id,
                "type": "function",
                "function": {
                    "name": "calculate",
                    "arguments": json.dumps({"expression": "2 + 2"}),
                },
            }
        ],
    }
    call = SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(
            name="calculate", arguments=json.dumps({"expression": "2 + 2"})
        ),
    )
    return FakeMessage(tool_calls=[call], wire_message=request_message), request_message


def fake_runner(monkeypatch, responses):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-used")
    completions = FakeCompletions(responses)
    client = SimpleNamespace(
        chat=SimpleNamespace(completions=completions)
    )
    return StrategyRunner(client=client), completions


def test_tool_loop_preserves_assistant_message_and_answers_tool_call_id(monkeypatch):
    tool_message, original_wire_message = fake_tool_call()
    runner, client = fake_runner(
        monkeypatch,
        [
            make_response(tool_message),
            make_response(FakeMessage(content="ANSWER: yes | 4")),
        ],
    )

    result = runner.with_tools(
        {"question": "What is 2 + 2?", "id": "Q-test"}, vague_lookup=False
    )

    second_request_messages = client.requests[1]["messages"]
    assert original_wire_message in second_request_messages
    tool_reply = next(message for message in second_request_messages if message["role"] == "tool")
    assert tool_reply["tool_call_id"] == "call-1"
    assert json.loads(tool_reply["content"]) == {"result": 4.0}
    assert result["answer_text"] == "ANSWER: yes | 4"
    assert result["tool_calls"][0]["tool_call_id"] == "call-1"


def test_tool_loop_marks_question_unanswered_at_round_limit(monkeypatch):
    responses = []
    for round_number in range(MAX_TOOL_ROUNDS):
        tool_message, _ = fake_tool_call(f"call-{round_number}")
        responses.append(make_response(tool_message))
    runner, client = fake_runner(monkeypatch, responses)

    result = runner.with_tools(
        {"question": "What is 2 + 2?", "id": "Q-test"}, vague_lookup=False
    )

    assert len(client.requests) == MAX_TOOL_ROUNDS
    assert result["round_limit_reached"] is True
    assert result["unanswered"] is True
