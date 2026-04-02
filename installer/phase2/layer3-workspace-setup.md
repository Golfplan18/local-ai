### PHASE 2, LAYER 3: WORKSPACE SETUP

**Stage Focus**: Verify the workspace directory structure from Phase 1 is complete and available.

The workspace directory was created in Phase 1, Layer 2. This layer verifies that the `models/` and `server/` directories exist and are accessible. It does not recreate the workspace.

### Processing Instructions

1. Verify the workspace root exists at the configured path.
2. Verify that `[workspace]/models/` and `[workspace]/server/` exist.
3. IF any required directory is missing (e.g., Phase 1 was interrupted), THEN recreate it.
4. Confirm model selection from Phase 2, Layer 2 is still available for Layer 5.

### Output Format for This Layer

```
WORKSPACE VERIFIED
Workspace root: [full path]
models/: [present]
server/: [present]
```

---

