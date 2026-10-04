"""Hypothesis model-based tests for all ten RPC operations."""

from tempfile import TemporaryDirectory

from hypothesis import HealthCheck, settings
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, invariant, rule

from src.rpc import RpcClient, start_background_server


@settings(
    max_examples=30,
    stateful_step_count=25,
    derandomize=True,
    suppress_health_check=[HealthCheck.too_slow],
    deadline=None,
)
class RpcMachine(RuleBasedStateMachine):
    """Compare RPC state with an independent dictionary oracle."""

    def __init__(self):
        super().__init__()
        self.temp = TemporaryDirectory()
        path = f"{self.temp.name}/journal.log"
        self.server, self.thread = start_background_server(journal_path=path)
        self.client = RpcClient(port=self.server.server_address[1])
        self.people = {}
        self.queries = {}
        self.results = {}
        self.next_id = 1

    def teardown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def _id(self):
        identifier = self.next_id
        self.next_id += 1
        return identifier

    @rule(locale=st.text(max_size=8), agent=st.text(max_size=8))
    def add_person(self, locale, agent):
        record = {
            "identifier": self._id(),
            "time": 1,
            "locale": locale,
            "user_agent": agent,
        }
        assert self.client.create_person(record) == record
        self.people[record["identifier"]] = record

    @rule(locale=st.text(max_size=8))
    def change_person(self, locale):
        if not self.people:
            return
        identifier = min(self.people)
        self.people[identifier]["locale"] = locale
        assert (
            self.client.edit_person(identifier, {"locale": locale})
            == self.people[identifier]
        )

    @rule(content=st.text(max_size=8), age=st.integers(-600, 600))
    def add_query(self, content, age):
        if not self.people:
            return
        record = {
            "identifier": self._id(),
            "time": 2_000_000 + age,
            "content": content,
            "person": min(self.people),
        }
        assert self.client.create_query(record) == record
        self.queries[record["identifier"]] = record

    @rule(content=st.text(max_size=8))
    def change_query(self, content):
        if not self.queries:
            return
        identifier = min(self.queries)
        self.queries[identifier]["content"] = content
        assert (
            self.client.edit_query(identifier, {"content": content})
            == self.queries[identifier]
        )

    @rule(output=st.text(max_size=8), duration=st.integers(0, 100))
    def add_result(self, output, duration):
        if not self.queries:
            return
        record = {
            "identifier": self._id(),
            "time": 2_000_000,
            "output": output,
            "state": "done",
            "failure": "",
            "query": min(self.queries),
            "duration": duration,
        }
        assert self.client.create_result(record) == record
        self.results[record["identifier"]] = record

    @rule(state=st.text(max_size=8))
    def change_result(self, state):
        if not self.results:
            return
        identifier = min(self.results)
        self.results[identifier]["state"] = state
        assert (
            self.client.edit_result(identifier, {"state": state})
            == self.results[identifier]
        )

    @rule()
    def reject_unknown_parent(self):
        record = {
            "identifier": self._id(),
            "time": 2_000_000,
            "content": "invalid",
            "person": -1,
        }
        try:
            self.client.create_query(record)
        except ValueError as error:
            assert "does not exist" in str(error)
        else:
            raise AssertionError("missing parent was accepted")

    @rule(text=st.text(max_size=8))
    def reject_invalid_person(self, text):
        record = {
            "identifier": self._id(),
            "time": 1,
            "locale": text,
            "user_agent": "agent",
        }
        self._expect_error(
            self.client.create_person,
            {"identifier": record["identifier"]},
            "expected fields",
        )
        self._expect_error(
            self.client.create_person,
            {**record, "time": "one"},
            "time must be int",
        )
        assert self.client.create_person(record) == record
        self.people[record["identifier"]] = record
        self._expect_error(self.client.create_person, record, "already exists")

    @rule()
    def reject_invalid_edits(self):
        if not self.people:
            return
        identifier = min(self.people)
        self._expect_error(
            self.client.edit_person,
            "bad",
            {"locale": "x"},
            "identifier must be int",
        )
        self._expect_error(
            self.client.edit_person, identifier, {}, "invalid changes"
        )
        self._expect_error(
            self.client.edit_person,
            identifier,
            {"unknown": "x"},
            "invalid changes",
        )
        self._expect_error(
            self.client.edit_person,
            identifier,
            {"identifier": identifier + 1},
            "cannot be changed",
        )
        self._expect_error(
            self.client.edit_person,
            identifier,
            {"time": "bad"},
            "time must be int",
        )

    @rule()
    def reject_invalid_result_and_time(self):
        record = {
            "identifier": self._id(),
            "time": 2_000_000,
            "output": "x",
            "state": "done",
            "failure": "",
            "query": -1,
            "duration": 1,
        }
        self._expect_error(self.client.create_result, record, "does not exist")
        self._expect_error(self.client.recent_queries, "bad", "now must be int")
        assert isinstance(self.client.recent_queries(), list)

    @staticmethod
    def _expect_error(method, *args):
        *parameters, message = args
        try:
            method(*parameters)
        except ValueError as error:
            assert message in str(error)
        else:
            raise AssertionError(f"expected error containing {message}")

    @invariant()
    def compare_complete_state(self):
        assert self.client.get_people() == list(self.people.values())
        assert self.client.get_queries() == list(self.queries.values())
        assert self.client.get_results() == list(self.results.values())
        expected = [
            {
                "locale": self.people[query["person"]]["locale"],
                "content": query["content"],
            }
            for query in self.queries.values()
            if query["time"] > 2_000_000 - 540
        ]
        assert self.client.recent_queries(now=2_000_000) == expected


TestRpcMachine = RpcMachine.TestCase
