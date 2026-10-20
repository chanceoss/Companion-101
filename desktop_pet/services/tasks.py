"""Explicit local conflict resolution; no remote writes or record deletion."""


def accept_cloud_copy(store, local_id, remote):
    task = store.task(local_id)
    if not task or task["external_id"] != remote.get("id"):
        raise ValueError("Refresh and select the matching cloud task first.")
    with store.connection() as db:
        db.execute("UPDATE tasks SET dirty=0,conflict='' WHERE id=?", (local_id,))
    store.merge_tasks(task["list_id"], [remote])


def link_existing_task(store, local_id, list_id, remote):
    task = store.task(local_id)
    if not task or task["external_id"]:
        raise ValueError("Choose an unlinked local task.")
    with store.connection() as db:
        duplicate = db.execute(
            "SELECT id,dirty FROM tasks WHERE source='google' AND list_id=? AND external_id=?",
            (list_id, remote["id"]),
        ).fetchone()
        if duplicate:
            if duplicate["dirty"]:
                raise ValueError(
                    "The imported copy has local changes. Resolve them first."
                )
            # An explicitly confirmed link merges only the redundant local cache.
            db.execute("DELETE FROM tasks WHERE id=?", (duplicate["id"],))
    store.link_task(local_id, list_id, remote)
