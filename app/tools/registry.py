from typing import Callable, Any

class ToolRegistry:
    def __init__(self):
        self._tools = {}

    def register(self, name: str, description: str, schema: dict, handler: Callable[..., Any]):
        self._tools[name] = {
            'name': name,
            'description': description,
            'schema': schema,
            'handler': handler
        }

    def get_tool(self, name: str):
        return self._tools.get(name)

    def get_all_tools(self):
        return list(self._tools.values())

    def get_definitions(self):
        definitions = []
        for tool in self._tools.values():
            definitions.append({
                "type": "function",
                "function": {
                    "name": tool['name'],
                    "description": tool['description'],
                    "parameters": tool['schema']
                }
            })
        return definitions

registry = ToolRegistry()
