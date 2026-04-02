### HARDWARE EVALUATION GATE

After Phase 1 completes, perform a brief hardware check to determine whether Phase 2 should execute.

IF total RAM is less than 8 GB, THEN:
- Report the hardware findings clearly.
- Inform the reader: "Your system is complete. You have access to commercial AI through browser automation at localhost:5000, all book frameworks are installed, and every thinking methodology in this book works identically on your setup. If you upgrade your hardware in the future, run this framework again to add local model capability."
- Proceed to Phase 1 completion (Documentation and Verification, extended version).
- This is NOT a failure state. Tier 0 is the same architecture on different hardware.

IF total RAM is 8 GB or greater AND available disk space is 5 GB or greater, THEN proceed to Phase 2.

---

## PHASE 2: ADDITIVE LOCAL CAPABILITY

*Phase 2 executes only if the reader's hardware supports local model execution (8GB+ RAM, 5GB+ disk). Phase 2 adds a local inference engine, a downloaded model, and registers the local model endpoint in the Phase 1 chat server. No new server is generated in Phase 2.*

---

