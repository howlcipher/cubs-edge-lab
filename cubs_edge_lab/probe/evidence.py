"""Minimal recorded API fields for portable, offline regeneration."""

import json

from .client import ApiError


def project(value, context=None):
    """Discard unused personal/statistical fields, retaining parser inputs."""
    keys = {
        "transactions",
        "id",
        "date",
        "description",
        "typeCode",
        "typeDesc",
        "person",
        "fromTeam",
        "toTeam",
        "teams",
        "league",
        "name",
        "people",
        "stats",
        "splits",
        "sport",
        "team",
        "season",
        "group",
        "displayName",
        "player",
        "totalSplits",
    }
    if isinstance(value, list):
        return [project(v, context) for v in value]
    if isinstance(value, dict):
        result = {
            k: project(v, k)
            for k, v in value.items()
            if k in keys and (k != "name" or context == "league")
        }
        if "stat" in value:
            result["stat"] = (
                {} if isinstance(value["stat"], dict) else value["stat"]
            )
        return result
    return value


def key(endpoint, params):
    return json.dumps([endpoint, params], sort_keys=True)


class Recorder:
    def __init__(self, client):
        self.client = client
        self.records = []

    def get(self, endpoint, **params):
        record = {"endpoint": endpoint, "params": params}
        try:
            value = project(self.client.get(endpoint, **params))
            # Monthly windows use only IDs for the union comparison.
            if (
                endpoint == "transactions"
                and params["startDate"][:7] == params["endDate"][:7]
                and isinstance(value.get("transactions"), list)
            ):
                value["transactions"] = [
                    {"id": r.get("id")} if isinstance(r, dict) else r
                    for r in value["transactions"]
                ]
        except ApiError as exc:
            record["failure"] = str(exc)
            self.records.append(record)
            raise
        record["response"] = value
        self.records.append(record)
        return value


class RecordedClient:
    def __init__(self, records):
        self.records = {key(r["endpoint"], r["params"]): r for r in records}
        if len(self.records) != len(records):
            raise ValueError("Duplicate evidence query")
        self.used = set()

    def get(self, endpoint, **params):
        query = key(endpoint, params)
        self.used.add(query)
        if query not in self.records:
            raise ApiError("Missing recorded query: " + query)
        record = self.records[query]
        if "failure" in record:
            raise ApiError(record["failure"])
        return record["response"]
