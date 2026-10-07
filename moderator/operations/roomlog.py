###################
# Created : 2026-10-06
# Purpose : Durable record of the room. The evidence is preserved.
# Notes   : Append-only JSONL. Events that evolve (speeches) are recorded
#           once when they start and again when they complete; on load the
#           last record for an event_id wins. A speech interrupted by a
#           moderator crash stays unfinished forever, which is correct.
###################

import json
import os
from dataclasses import asdict
from datetime import datetime

from idiots.idiot import RoomEvent


class RoomLog:
    def __init__(self, path):
        directory = os.path.dirname(path)

        if directory:
            os.makedirs(directory, exist_ok=True)

        self._path = path
        self._file = open(path, "a")

    def load(self):
        events = {}

        try:
            with open(self._path) as file:
                for line in file:
                    line = line.strip()

                    if line:
                        record = json.loads(line)

                        # A suppressed N_S leaves only its empty opening line
                        # behind. An empty, unfinished speech is nothing.
                        if (
                            record.get("event_type") == "speech"
                            and not record.get("content")
                            and not record.get("complete")
                        ):
                            continue

                        if isinstance(record.get("started_at"), str):
                            record["started_at"] = datetime.fromisoformat(record["started_at"])

                        events[record["event_id"]] = record
        except FileNotFoundError:
            pass

        return [RoomEvent(**record) for record in events.values()]

    def record(self, event: RoomEvent):
        data = asdict(event)
        data["started_at"] = data["started_at"].isoformat()
        self._file.write(json.dumps(data) + "\n")
        self._file.flush()
