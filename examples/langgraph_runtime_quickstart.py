"""
Runtime-style LangGraph adapter quickstart using a fake builder.

Run: python examples/langgraph_runtime_quickstart.py
"""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from forkit.sdk import ForkitClient
from forkit.schemas import TaskType
from forkit_langgraph import LangGraphAdapter


class FakeBuilder:
    def __init__(self) -> None:
        self.name = "triage-builder"
        self.nodes = {"router": object(), "writer": object()}
        self.edges = {("START", "router"), ("router", "writer")}
        self.waiting_edges = {(("writer",), "END")}

    def compile(self, **kwargs):
        return FakeCompiledGraph(self, kwargs)


class FakeCompiledGraph:
    def __init__(self, builder: FakeBuilder, compile_kwargs: dict[str, object]) -> None:
        self.builder = builder
        self.compile_kwargs = compile_kwargs

    def get_name(self) -> str:
        return "compiled-triage-graph"

    def invoke(self, payload):
        return {"ok": True, "payload": payload}


REGISTRY_ROOT = "/tmp/forkit-langgraph-runtime-demo"
CREATOR = {"name": "Hamza", "organization": "ForkIt"}

client = ForkitClient(registry_root=REGISTRY_ROOT)
adapter = LangGraphAdapter(client=client)
builder = FakeBuilder()

model_id = client.models.register(
    name="langgraph-runtime-model",
    version="1.0.0",
    task_type=TaskType.TEXT_GENERATION,
    architecture="transformer",
    creator=CREATOR,
)

compiled, passport_id = adapter.compile_and_register(
    builder,
    compile_kwargs={"name": "triage-runtime", "debug": True},
    name="triage-runtime-graph",
    version="1.0.0",
    model_id=model_id,
    creator=CREATOR,
    system_prompt="Route work to the right node.",
)

bound = adapter.bind_graph(
    compiled,
    name="triage-runtime-graph-lazy",
    version="1.0.1",
    model_id=model_id,
    creator=CREATOR,
    system_prompt="Route work to the right node.",
)
result = bound.invoke({"question": "hello"})

print(f"Compiled graph passport: {passport_id[:16]}...")
print(f"Lazy bound passport: {bound.passport_id[:16]}...")
print(f"Invoke result: {result}")
