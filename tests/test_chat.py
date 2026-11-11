from pathlib import Path
import json
import os
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import pandas as pd
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
os.environ.setdefault("FPL_SESSIONS_DB_PATH", ":memory:")

os.environ["FPL_API_TOKEN"] = ""  # the tests run without the API token, whatever .env says
import api
import chat
from test_api import fake_team


def text(value):
    return SimpleNamespace(type="text", text=value)


def tool_use(name, args, block_id="t1"):
    return SimpleNamespace(type="tool_use", id=block_id, name=name, input=args)


def message(*content, stop_reason=None):
    usage = SimpleNamespace(input_tokens=10, output_tokens=5, cache_read_input_tokens=7, cache_creation_input_tokens=0)
    stop = stop_reason or ("tool_use" if any(b.type == "tool_use" for b in content) else "end_turn")
    return SimpleNamespace(content=list(content), stop_reason=stop, usage=usage)


class FakeStream:
    def __init__(self, response):
        self.response = response

    def __enter__(self):
        if isinstance(self.response, Exception):
            raise self.response
        return self

    def __exit__(self, *exc):
        return False

    def __iter__(self):
        for block in self.response.content:
            if block.type == "text":
                yield SimpleNamespace(type="text", text=block.text)
            else:
                yield SimpleNamespace(type="content_block_start", content_block=block)

    def get_final_message(self):
        return self.response


class FakeAnthropic:
    """Scripted Claude: returns the responses in order and records what each request sent."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(stream=self.stream))

    def stream(self, **request):
        self.requests.append({**request, "messages": list(request["messages"])})
        return FakeStream(self.responses.pop(0))


def run(conversation, api_client, question="Sell Haaland?", team_sig="t1", page_sig="p1", execute=None, calls=None):
    calls = calls if calls is not None else []
    execute = execute or (lambda name, args: (calls.append((name, args)) or '{"ok":true}', False))
    return list(chat.respond(conversation, api_client, question, team_sig, lambda: "<team_state>T</team_state>",
                             page_sig, lambda: "<page>P</page>", execute))


class RespondTests(unittest.TestCase):
    def conversation(self):
        return chat.Conversation("forecast", [{"type": "text", "text": "system"}])

    def test_tool_round_then_answer_keeps_an_append_only_history(self):
        convo, calls = self.conversation(), []
        fake = FakeAnthropic(message(tool_use("transfers", {"number": 1, "outgoing_ids": [411]})), message(text("Keep him.")))
        events = run(convo, fake, calls=calls)
        self.assertEqual(calls, [("transfers", {"number": 1, "outgoing_ids": [411]})])
        self.assertEqual([m["role"] for m in convo.messages], ["user", "system", "assistant", "user", "assistant"])
        self.assertIn("<team_state>T</team_state>", convo.messages[1]["content"])
        self.assertEqual(convo.messages[3]["content"][0]["tool_use_id"], "t1")
        self.assertIn({"type": "text", "text": "Keep him."}, events)
        self.assertEqual(events[-1]["type"], "done")
        self.assertEqual(events[-1]["usage"]["cache_read_input_tokens"], 14)
        self.assertEqual(fake.requests[0]["model"], "claude-opus-5-5")
        self.assertEqual(fake.requests[0]["output_config"], {"effort": "low"})
        self.assertEqual(fake.requests[0]["cache_control"], {"type": "ephemeral", "ttl": "1h"})
        self.assertEqual(chat.transcript(convo), [{"role": "user", "text": "Sell Haaland?"},
                                                  {"role": "assistant", "text": "Keep him."}])

    def test_unchanged_context_is_not_resent_and_earlier_turns_stay_identical(self):
        convo = self.conversation()
        run(convo, FakeAnthropic(message(text("First."))))
        first_turn = list(convo.messages)
        fake = FakeAnthropic(message(text("Second.")))
        run(convo, fake, question="And captain?")
        self.assertEqual(fake.requests[0]["messages"][:len(first_turn)], first_turn)
        self.assertEqual([m["role"] for m in convo.messages[len(first_turn):]], ["user", "assistant"])
        run(convo, FakeAnthropic(message(text("Third."))), question="Now?", page_sig="p2")
        self.assertEqual(convo.messages[-2], {"role": "system", "content": "<page>P</page>"})

    def test_failure_or_refusal_rolls_the_turn_back(self):
        for response in (RuntimeError("network down"), message(stop_reason="refusal")):
            convo = self.conversation()
            events = run(convo, FakeAnthropic(response))
            self.assertEqual(events[-1]["type"], "error")
            self.assertEqual((convo.messages, convo.team_sig, convo.page_sig), ([], "", ""))
            self.assertFalse(convo.lock.locked())

    def test_rejected_fallbacks_are_dropped_and_the_question_retried(self):
        rejected = RuntimeError("'fallbacks' is not supported for this model")
        rejected.status_code = 400
        fake = FakeAnthropic(rejected, message(text("Fine.")))
        with patch.dict(chat.FALLBACK):
            events = run(self.conversation(), fake)
            self.assertEqual(chat.FALLBACK, {})
        self.assertEqual(fake.requests[0]["fallbacks"], "default")
        self.assertNotIn("fallbacks", fake.requests[1])
        self.assertEqual(events[-1]["type"], "done")

    def test_a_second_question_while_answering_is_refused(self):
        convo = self.conversation()
        convo.lock.acquire()
        self.assertEqual(run(convo, FakeAnthropic())[0]["type"], "error")

    def test_runaway_tool_loop_stops_and_rolls_back(self):
        convo = self.conversation()
        fake = FakeAnthropic(*[message(tool_use("strategy", {})) for _ in range(chat.MAX_TOOL_ROUNDS + 1)])
        self.assertEqual(run(convo, fake)[-1]["type"], "error")
        self.assertEqual(convo.messages, [])


class StoreAndSnapshotTests(unittest.TestCase):
    def test_new_forecast_starts_a_new_conversation(self):
        store = chat.ChatStore()
        old, new = (SimpleNamespace(forecast_path=Path(p), target_event=5) for p in ("a.csv", "b.csv"))
        with patch.object(chat, "build_system", return_value=[]):
            first, replaced = store.get("s", old, Path("."))
            self.assertFalse(replaced)
            first.messages.append({"role": "user", "content": "hi"})
            self.assertIs(store.get("s", old, Path("."))[0], first)
            second, replaced = store.get("s", new, Path("."))
        self.assertTrue(replaced)
        self.assertEqual(second.messages, [])

    def test_key_is_read_from_dotenv_on_every_request(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ANTHROPIC_API_KEY", None)
            env = Path(directory) / ".env"
            env.write_text("ANTHROPIC_API_KEY=\n")
            self.assertIsNone(chat.client(Path(directory)))
            env.write_text("ANTHROPIC_API_KEY=sk-ant-test\n")
            self.assertEqual(chat.client(Path(directory)).api_key, "sk-ant-test")

    def test_market_tables_have_every_gameweek_and_the_fixture_grid(self):
        weekly = pd.DataFrame([
            {"id": 1, "name": "A", "position": "FWD", "team": "MCI", "price": 150, "opponent": "FUL (H)",
             "recommended_points": 6.0, "recommended_q10": 1.0, "recommended_q90": 13.0, "forecast_event": e}
            for e in (5, 6)] + [{"id": 2, "name": "Benchwarmer", "position": "DEF", "team": "MCI", "price": 40,
                                 "opponent": "FUL (H)", "recommended_points": 0.2, "forecast_event": e} for e in (5, 6)])
        tables = chat.market_tables(weekly)
        self.assertNotIn("Benchwarmer", tables)
        self.assertIn("1 players with under 1 xP", tables)
        self.assertIn("xp_gw5,xp_gw6,xp_total", tables)
        self.assertIn("1,A,FWD,MCI,150,6.0,6.0,12.0,2.0,26.0", tables)
        self.assertIn("MCI,FUL (H),FUL (H)", tables)


class ChatApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(api.app)
        api.RESULTS = api.ResultCache()
        api.CHATS = chat.ChatStore()
        for target in (patch.object(api, "_warm"), patch.object(chat, "build_system", return_value=[])):
            target.start()
            self.addCleanup(target.stop)
        self.session = api.STORE.add(fake_team())

    def test_tools_add_claudes_exclusions_to_the_users_own(self):
        with patch.object(api, "transfers", side_effect=lambda sid, request: request.model_dump()):
            execute = api._chat_executor(api._chat_tools(self.session, {"locked_ids": [], "excluded_ids": [2]}))
            content, failed = execute("transfers", {"number": 1, "excluded_ids": [3]})
        self.assertFalse(failed)
        self.assertEqual(json.loads(content)["excluded_ids"], [2, 3])

    def test_tool_errors_reach_claude_instead_of_failing_the_chat(self):
        execute = api._chat_executor(api._chat_tools(self.session, {}))
        content, failed = execute("compare_players", {"out_id": 999, "in_id": 2})
        self.assertTrue(failed)
        self.assertIn("owned", content)
        self.assertTrue(execute("transfers", {"number": 9})[1])
        self.assertEqual(execute("write_squad", {}), ("Unknown tool write_squad.", True))

    def test_missing_key_explains_what_to_do(self):
        with patch.object(chat, "client", return_value=None):
            response = self.client.post(f"/api/team/{self.session}/chat", json={"message": "hi"})
            history = self.client.get(f"/api/team/{self.session}/chat").json()
        self.assertEqual(response.status_code, 503)
        self.assertIn("ANTHROPIC_API_KEY", response.json()["detail"])
        self.assertFalse(history["enabled"])

    def test_chat_streams_events_with_team_and_page_context(self):
        fake = FakeAnthropic(message(text("Hold.")))
        with patch.object(chat, "client", return_value=fake), \
                patch.object(api, "_chat_team_block", return_value="<team_state>T</team_state>"):
            response = self.client.post(f"/api/team/{self.session}/chat", json={
                "message": "Sell?", "page": {"view": "transfers", "label": "Transfers",
                                             "calls": [{"tool": "lineup_value", "args": {}}, {"tool": "update_squad"}]}})
        events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
        self.assertEqual(response.headers["content-type"].split(";")[0], "text/event-stream")
        self.assertIn({"type": "text", "text": "Hold."}, events)
        self.assertEqual(events[-1]["type"], "done")
        context_message = fake.requests[0]["messages"][1]
        self.assertEqual(context_message["role"], "system")
        self.assertIn("<team_state>T</team_state>", context_message["content"])
        self.assertIn("Transfers (page 'transfers')", context_message["content"])
        self.assertIn("[lineup_value {}]", context_message["content"])
        self.assertNotIn("update_squad", context_message["content"])
        history = self.client.get(f"/api/team/{self.session}/chat").json()["messages"]
        self.assertEqual(history[-1], {"role": "assistant", "text": "Hold."})
        self.assertEqual(self.client.post(f"/api/team/{self.session}/chat/reset").json(), {"messages": []})


if __name__ == "__main__":
    unittest.main()
