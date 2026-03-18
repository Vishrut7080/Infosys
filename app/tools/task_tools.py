"""Agent tools for task/to-do management."""

from app.tools.registry import registry
from app.database import database


def add_task_handler(user_email: str, title: str, description: str = '', priority: str = 'normal'):
    """Create a new task for the user."""
    if not title or not title.strip():
        return "Error: Task title is required."
    task = database.add_task(user_email, title.strip(), description.strip(), priority)
    return f"Task created (#{task['id']}): \"{task['title']}\" — priority: {task['priority']}"


def list_tasks_handler(user_email: str, status: str = 'pending'):
    """List the user's tasks, filtered by status."""
    valid = {'pending', 'done', 'all'}
    if status not in valid:
        status = 'pending'
    tasks = database.list_tasks(user_email, status)
    if not tasks:
        label = 'tasks' if status == 'all' else f'{status} tasks'
        return f"You have no {label}."
    lines = [f"{'✅' if t['status'] == 'done' else '⏳'} [{t['id']}] {t['title']} ({t['priority']})" for t in tasks]
    return f"Your {status} tasks ({len(tasks)}):\n" + "\n".join(lines)


def complete_task_handler(user_email: str, task_id: int):
    """Mark a task as completed."""
    updated = database.complete_task(user_email, int(task_id))
    if updated:
        return f"Task #{task_id} marked as completed."
    return f"Error: Task #{task_id} not found or already completed."


def delete_task_handler(user_email: str, task_id: int):
    """Delete a task permanently."""
    deleted = database.delete_task(user_email, int(task_id))
    if deleted:
        return f"Task #{task_id} deleted."
    return f"Error: Task #{task_id} not found."


registry.register(
    name="add_task",
    description="Create a new task or to-do item for the user.",
    schema={
        "type": "object",
        "properties": {
            "title":       {"type": "string",  "description": "Short title for the task"},
            "description": {"type": "string",  "description": "Optional longer description"},
            "priority":    {"type": "string",  "enum": ["normal", "high", "urgent"], "description": "Task priority (default: normal)"}
        },
        "required": ["title"]
    },
    handler=add_task_handler
)

registry.register(
    name="list_tasks",
    description="List the user's tasks. Filter by status: 'pending' (default), 'done', or 'all'.",
    schema={
        "type": "object",
        "properties": {
            "status": {"type": "string", "enum": ["pending", "done", "all"], "description": "Filter by task status (default: pending)"}
        },
        "required": []
    },
    handler=list_tasks_handler
)

registry.register(
    name="complete_task",
    description="Mark a task as completed by its numeric ID.",
    schema={
        "type": "object",
        "properties": {
            "task_id": {"type": "integer", "description": "The numeric ID of the task to complete"}
        },
        "required": ["task_id"]
    },
    handler=complete_task_handler
)

registry.register(
    name="delete_task",
    description="Permanently delete a task by its numeric ID.",
    schema={
        "type": "object",
        "properties": {
            "task_id": {"type": "integer", "description": "The numeric ID of the task to delete"}
        },
        "required": ["task_id"]
    },
    handler=delete_task_handler
)
