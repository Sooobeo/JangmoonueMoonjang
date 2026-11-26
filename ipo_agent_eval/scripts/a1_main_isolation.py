"""Offline capture of CLI tool exposure with a synthetic, deliberately rejected tool call."""
import json
import subprocess
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from scripts.a1_main_blind import BASE, MODEL, CATALOG, command, hash_bytes, prepare_catalog, wire, write_once


def isolation_check():
    prepare_catalog()
    steps = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            self.send_error(404)

        def do_POST(self):
            request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            produce_answer = "synthetic success" in json.dumps(request["input"])
            exposed = list(request.get("tools", []))
            for row in request["input"]:
                exposed.extend(row.get("tools", []))
            names = []
            for tool in exposed:
                if tool["type"] == "namespace":
                    names.extend(tool["name"]+"."+t["name"] for t in tool["tools"])
                else:
                    names.append(tool.get("name",tool["type"]))
            outputs = [r["output"] for r in request["input"] if r["type"] == "function_call_output"]
            steps.append({"tools": names, "outputs": outputs, "model": request["model"],
                          "reasoning": request["reasoning"]})
            if not produce_answer and (outputs or len(steps)>1 or not names):
                self.send_error(400)
                return
            item = {"type":"function_call","call_id":"call_probe","id":"fc_probe",
                    "name":"request_user_input","namespace":"functions",
                    "arguments":json.dumps({"questions":[{"header":"Test","id":"probe",
                      "question":"Reply?", "options":[{"label":"A","description":"A"},{"label":"B","description":"B"}]}]})}
            if produce_answer:
                item={"type":"message","id":"msg_a1","role":"assistant","status":"completed",
                      "content":[{"type":"output_text","text":'{"x":"ok"}',"annotations":[]}]}
            events = [{"type":"response.created","response":{"id":"resp_a1"}},
                      {"type":"response.output_item.added","output_index":0,"item":item},
                      {"type":"response.output_item.done","output_index":0,"item":item},
                      {"type":"response.completed","response":{"id":"resp_a1","status":"completed",
                       "output":[item],"usage":{"input_tokens":1,"output_tokens":1,"total_tokens":2}}}]
            body = "".join("event: "+e["type"]+"\ndata: "+json.dumps(e)+"\n\n" for e in events).encode()
            self.send_response(200)
            self.send_header("Content-Type","text/event-stream")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
    with ThreadingHTTPServer(("127.0.0.1",0), Handler) as server, tempfile.TemporaryDirectory() as tmp:
        thread = threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        root = Path(tmp)
        work = root / "empty"
        work.mkdir()
        schema = root / "schema.json"
        schema.write_bytes(wire({"type":"object","properties":{"x":{"type":"string"}},
                                 "required":["x"],"additionalProperties":False}))
        cfg = ('model_provider="offline_probe"', 'model_providers.offline_probe.name="loopback"',
               f'model_providers.offline_probe.base_url="http://127.0.0.1:{server.server_port}/v1"',
               'model_providers.offline_probe.wire_api="responses"', 'model_providers.offline_probe.request_max_retries=0')
        try:
            proc = subprocess.run(command(work,schema,[s for v in cfg for s in ("-c",v)]),
                                  input=b"synthetic packet", cwd=work, timeout=30,capture_output=True)
            rejected_steps=steps.copy()
            success = subprocess.run(command(work,schema,[s for v in cfg for s in ("-c",v)]),
                                  input=b"synthetic success", cwd=work, timeout=30,capture_output=True)
        finally:
            server.shutdown()
            thread.join()
    if not steps or any(step["model"]!=MODEL or step["reasoning"].get("effort")!="medium"
                        or set(step["tools"])-{"functions.request_user_input"} for step in steps):
        raise ValueError(f"Unexpected model or active tool surface: {steps}")
    if steps[0]["tools"] and (rejected_steps[-1]["outputs"] != ["request_user_input is unavailable in Default mode"]
                             or b"tools::router" not in proc.stderr):
        raise ValueError("Cannot reject and detect interactive tool call")
    messages=[json.loads(line) for line in success.stdout.splitlines() if line.strip()]
    answers=[e["item"]["text"] for e in messages if e["type"]=="item.completed"
             and e["item"]["type"]=="agent_message"]
    if success.returncode or len(answers)!=1 or json.loads(answers[0])!={"x":"ok"}:
        raise ValueError("Could not replay a fully structured synthetic Codex response")
    write_once(BASE/"codex_mock_submission.json",wire({"validated_answer":{"x":"ok"},
               "turn_usage_present":any(e.get("usage") for e in messages),"no_active_tools":True}))
    cli = Path(command(work,schema)[0])
    result = {"codex_binary_sha256":hash_bytes(cli.read_bytes()), "catalog_sha256":hash_bytes(CATALOG.read_bytes()),
              "version":subprocess.check_output([str(cli),"--version"]).decode().strip(),
              "capture":rejected_steps,"synthetic_loopback_only":True, "active_tools":[]}
    write_once(BASE/"isolation.json", wire(result))
    return result


if __name__ == "__main__":
    print(json.dumps(isolation_check(), ensure_ascii=True))
