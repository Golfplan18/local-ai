### PHASE 2, LAYER 6: LOCAL ENDPOINT REGISTRATION AND ROUTING VERIFICATION

**Stage Focus**: Register the local model endpoint in the Phase 1 chat server and verify that the server routes to it correctly. The chat server (`[workspace]/server/server.py`) was installed in Phase 1, Layer 7. This layer does not regenerate it.

### Processing Instructions

1. The chat server (`[workspace]/server/server.py`) was installed in Phase 1, Layer 7. Do not regenerate it.
2. The local model endpoint was installed in Layers 4–5. Add it to the endpoint registry at `[workspace]/config/endpoints.json`:

   ```json
   {
     "name": "local-[engine]",
     "type": "local",
     "engine": "[mlx|ollama]",
     "model": "[model_name]",
     "url": "[localhost endpoint URL]",
     "status": "active"
   }
   ```

3. Verify the endpoint appears in `endpoints.json` with status "active".
4. Update the default endpoint in the registry to the local model:

   ```json
   "default_endpoint": "local-[engine]"
   ```

5. Test routing to the local model:
   a. Ensure the local inference engine is running (`ollama serve` or equivalent for MLX).
   b. Start the chat server: `python3 [workspace]/server/server.py &`
   c. Send a test request: "What model are you running on?"
   d. Verify the response identifies the local model (not a commercial AI service).
   e. Stop the server.

   IF the test fails: check that the inference engine is running and that the endpoint URL in the registry matches the running service.

6. Confirm tool access is still functional with the local model:
   a. Start the server and send a test request: "Search the web for today's date."
   b. Verify tool execution produces a real result.
   c. Stop the server.

   IF tool execution fails with the local model but worked with the commercial AI endpoint: the local model may not be reliably emitting tool call XML. Add a note to the hardware report: "Local model [name] may require explicit tool call instructions. If tool calls are not triggering, try pasting the tool call example from boot.md into your request."

### Output Format for This Layer

```
LOCAL MODEL ENDPOINT REGISTERED
Model: [model name]
Endpoint URL: [localhost URL]
Registry entry: [ADDED / ALREADY EXISTS]
Default endpoint: updated to local model
Routing test: [PASS / FAIL]
Tool execution test: [PASS / FAIL]
```

---

