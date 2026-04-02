### PHASE 2, LAYER 1: HARDWARE EVALUATION

**Stage Focus**: Discover the user's hardware capabilities and constraints. Make no assumptions — measure everything.

**Input**: Access to the local operating system via terminal commands.

**Output**: A hardware profile containing: operating system name and version, processor type and architecture, total RAM in gigabytes, available disk space in gigabytes, and GPU type if applicable.

### Processing Instructions

1. Detect the operating system.
   - IF macOS: execute `sw_vers` for version, `uname -m` for architecture.
   - IF Linux: execute `cat /etc/os-release` for distribution, `uname -m` for architecture.
   - IF Windows: execute `systeminfo` and parse OS Name, OS Version, and System Type.

2. Detect total RAM.
   - IF macOS: execute `sysctl -n hw.memsize` and convert bytes to gigabytes.
   - IF Linux: execute `free -b` and parse the "Mem: total" value, convert to gigabytes.
   - IF Windows: execute `wmic memorychip get capacity` and sum all values, convert to gigabytes.

3. Detect available disk space.
   - IF macOS or Linux: execute `df -h ~` and parse the "Avail" column for the home directory mount.
   - IF Windows: execute `wmic logicaldisk where "DeviceID='C:'" get FreeSpace` and convert to gigabytes.

4. Detect processor details.
   - IF macOS: execute `sysctl -n machdep.cpu.brand_string` for CPU name. Execute `system_profiler SPHardwareDataType` and parse for chip type (Apple M-series vs. Intel).
   - IF Linux: execute `lscpu` and parse Model name, Architecture, and check for GPU via `lspci | grep -i nvidia`.
   - IF Windows: parse processor info from `systeminfo` output. Check for NVIDIA GPU via `nvidia-smi` (if available).

5. Determine Apple Silicon status.
   - IF macOS AND architecture is `arm64`, THEN set APPLE_SILICON = true.
   - IF macOS AND architecture is `x86_64`, THEN set APPLE_SILICON = false.
   - IF not macOS, THEN set APPLE_SILICON = false.

6. Determine NVIDIA GPU status.
   - IF Linux or Windows AND `nvidia-smi` executes successfully, THEN set HAS_NVIDIA_GPU = true and record GPU model and VRAM.
   - ELSE set HAS_NVIDIA_GPU = false.

### Output Format for This Layer

```
HARDWARE EVALUATION RESULTS
Operating System: [name and version]
Processor: [name]
Architecture: [arm64 / x86_64 / etc.]
Apple Silicon: [Yes / No]
NVIDIA GPU: [Yes (model, VRAM) / No]
Total RAM: [X] GB
Available Disk Space: [X] GB
Available Model RAM (75% of total): [X] GB
```

### Invariant Check

Before proceeding: confirm that all four hardware dimensions (OS, RAM, disk, processor) were measured, not assumed. Confirm that AVAILABLE_MODEL_RAM has been calculated as total RAM × 0.75. These values must persist accurately through all subsequent layers.

---

