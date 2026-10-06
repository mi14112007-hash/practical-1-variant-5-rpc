"""List-backed in-memory data model for Person, Query and Result."""

from copy import deepcopy
from threading import RLock
from time import time

SCHEMAS = {
    "person": {
        "identifier": int,
        "time": int,
        "locale": str,
        "user_agent": str,
    },
    "query": {
        "identifier": int,
        "time": int,
        "content": str,
        "person": int,
    },
    "result": {
        "identifier": int,
        "time": int,
        "output": str,
        "state": str,
        "failure": str,
        "query": int,
        "duration": int,
    },
}
WINDOW_SECONDS = 9 * 60
OPERATIONS = (
    "create_person",
    "get_people",
    "edit_person",
    "create_query",
    "get_queries",
    "edit_query",
    "create_result",
    "get_results",
    "edit_result",
    "recent_queries",
)


class DataModel:
    """Store records in lists and expose ten data operations."""

    def __init__(self):
        self.people = []
        self.queries = []
        self.results = []
        self.lock = RLock()

    def _table(self, entity):
        return {
            "person": self.people,
            "query": self.queries,
            "result": self.results,
        }[entity]

    def _validate(self, entity, record):
        schema = SCHEMAS[entity]
        if set(record) != set(schema):
            raise ValueError(f"{entity}: expected fields {sorted(schema)}")
        for field, kind in schema.items():
            if type(record[field]) is not kind:
                raise ValueError(f"{field} must be {kind.__name__}")
        if entity == "query":
            self._require("person", record["person"])
        if entity == "result":
            self._require("query", record["query"])

    def _require(self, entity, identifier):
        for record in self._table(entity):
            if record["identifier"] == identifier:
                return record
        raise ValueError(f"{entity} {identifier} does not exist")

    def _create(self, entity, record):
        with self.lock:
            self._validate(entity, record)
            if any(
                item["identifier"] == record["identifier"]
                for item in self._table(entity)
            ):
                raise ValueError(f"{entity} identifier already exists")
            saved = deepcopy(record)
            self._table(entity).append(saved)
            return deepcopy(saved)

    def _all(self, entity):
        with self.lock:
            return deepcopy(self._table(entity))

    def _edit(self, entity, identifier, changes):
        with self.lock:
            if type(identifier) is not int:
                raise ValueError("identifier must be int")
            if not changes or not set(changes) <= set(SCHEMAS[entity]):
                raise ValueError("invalid changes")
            if "identifier" in changes:
                raise ValueError("identifier cannot be changed")
            original = self._require(entity, identifier)
            updated = {**original, **changes}
            self._validate(entity, updated)
            original.update(deepcopy(changes))
            return deepcopy(original)

    def create_person(self, record):
        """Create one Person record."""
        return self._create("person", record)

    def get_people(self):
        """Return every Person record."""
        return self._all("person")

    def edit_person(self, identifier, changes):
        """Update fields of one Person record."""
        return self._edit("person", identifier, changes)

    def create_query(self, record):
        """Create one Query record linked to a Person."""
        return self._create("query", record)

    def get_queries(self):
        """Return every Query record."""
        return self._all("query")

    def edit_query(self, identifier, changes):
        """Update fields of one Query record."""
        return self._edit("query", identifier, changes)

    def create_result(self, record):
        """Create one Result record linked to a Query."""
        return self._create("result", record)

    def get_results(self):
        """Return every Result record."""
        return self._all("result")

    def edit_result(self, identifier, changes):
        """Update fields of one Result record."""
        return self._edit("result", identifier, changes)

    def recent_queries(self, now=None):
        """Right-join recent queries to people and project locale/content."""
        current = int(time()) if now is None else now
        if type(current) is not int:
            raise ValueError("now must be int")
        with self.lock:
            people_by_id = {
                person["identifier"]: person for person in self.people
            }
            return [
                {
                    "locale": (
                        people_by_id[query["person"]]["locale"]
                        if query["person"] in people_by_id
                        else None
                    ),
                    "content": query["content"],
                }
                for query in self.queries
                if query["time"] > current - WINDOW_SECONDS
            ]
