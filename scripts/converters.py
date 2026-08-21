#!/usr/bin/env python3
"""Provision the two programs Ora renders Word and PDF exports through.

Markdown is Ora's canonical format. Word (.docx) and PDF are render targets:
Ora hands the markdown to **Pandoc**, and Pandoc uses **Typst** as its PDF
engine. Both are separate programs. Neither ships inside this repository, and
until this script runs on a machine that has neither, Word and PDF export
report themselves unavailable.

Why download instead of shipping copies
---------------------------------------
Pandoc is GPL-2.0-or-later; Typst is Apache-2.0. Committing a Pandoc binary
into a tree the project releases to the public domain would be redistributing
GPL software under terms that contradict its licence. Downloading the
publisher's own release on the user's machine is not redistribution, so the
licence question never arises and the user still ends up with working export.

Why not "just use Homebrew"
---------------------------
"Works out of the box" cannot mean "works if you already have Homebrew". A Mac
with no Homebrew and a Windows machine with no WinGet or Chocolatey both have
to end up with working converters, so this fetches the publishers' official
release archives directly and needs no package manager at all.

What it does, once per converter
--------------------------------
1. Ask ``orchestrator.export`` whether the machine already has the program —
   ``PATH`` first, then the package-manager and official-installer
   directories that module already knows about. Found is found: nothing is
   downloaded, and the existing copy is what Ora uses.
2. Otherwise download the pinned release archive for this operating system and
   processor, straight from the publisher's own GitHub release page.
3. Refuse the download unless its SHA-256 matches the digest pinned in
   ``RELEASES`` below. The archive is held in memory until it has passed, so a
   file that fails the check never reaches the disk at all.
4. Unpack the single program out of the archive into
   ``<ORA_HOME>/data/converters/bin`` — the directory ``export.py`` searches
   right after ``PATH`` — and run it once to confirm it really executes. A
   program that will not run is removed again, so a failed attempt leaves the
   machine exactly as it found it and the retry command really does retry.

Nothing here is fatal. A converter that cannot be provisioned prints why, and
prints the one command that retries it; the rest of Ora is unaffected.

Usage:
    python3 scripts/install.py converters     # the retry command
    python3 scripts/converters.py --dry-run   # report, change nothing
    python3 scripts/converters.py --force     # re-fetch even if present
"""

from __future__ import annotations

import argparse
import hashlib
import io
import os
import platform
import subprocess
import sys
import tarfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from orchestrator import export  # noqa: E402
from orchestrator import network_policy  # noqa: E402

RETRY_COMMAND = "python3 scripts/install.py converters"

# Pinned releases. Bumping a version means re-pinning every digest.
PANDOC_VERSION = "3.10.2"
TYPST_VERSION = "0.15.1"

_PANDOC_BASE = f"https://github.com/jgm/pandoc/releases/download/{PANDOC_VERSION}"
_TYPST_BASE = f"https://github.com/typst/typst/releases/download/v{TYPST_VERSION}"

# No release archive is anywhere near this large; the cap stops a redirect to
# something else from filling the disk.
MAX_ARCHIVE_BYTES = 128 * 1024 * 1024
DOWNLOAD_TIMEOUT_SEC = 300
VERIFY_TIMEOUT_SEC = 60


@dataclass(frozen=True)
class Release:
    """One publisher archive and the single program to take out of it."""

    url: str
    sha256: str
    member: str  # exact path inside the archive — never a pattern
    binary: str  # the filename it is stored under


@dataclass
class Result:
    """What happened to one converter on this machine."""

    tool: str
    status: str  # "present" | "installed" | "would-install" | "failed"
    detail: str
    path: str | None = None

    @property
    def ok(self) -> bool:
        return self.status != "failed"


class ConverterError(Exception):
    """A converter could not be provisioned. Always reported, never raised out."""


# Digests below were taken from the publishers' GitHub releases and
# re-computed from the downloaded bytes when they were pinned (2026-08-21).
# GitHub reports the same SHA-256 for each asset through its releases API, so
# the two agree; the value living here is what matters, because a pin in this
# repository is what a later download has to match.
#
# Windows-on-ARM deliberately maps to the x86_64 archives: Pandoc publishes no
# ARM build for Windows, and Windows 11 on ARM runs x64 programs through its
# own emulator, so one archive set covers both Windows processors.
RELEASES: dict[str, dict[str, Release]] = {
    "pandoc": {
        "darwin-arm64": Release(
            url=f"{_PANDOC_BASE}/pandoc-{PANDOC_VERSION}-arm64-macOS.zip",
            sha256="a30bd546062f0b29c25f45a71f951b7a1cf4f998d5b43974ea2c2416133f2e99",
            member=f"pandoc-{PANDOC_VERSION}-arm64/bin/pandoc",
            binary="pandoc",
        ),
        "darwin-x86_64": Release(
            url=f"{_PANDOC_BASE}/pandoc-{PANDOC_VERSION}-x86_64-macOS.zip",
            sha256="437d378af72e9648f6fb42c170031218a3c2f31cf5089234cf2d0413f91481d0",
            member=f"pandoc-{PANDOC_VERSION}-x86_64/bin/pandoc",
            binary="pandoc",
        ),
        "linux-x86_64": Release(
            url=f"{_PANDOC_BASE}/pandoc-{PANDOC_VERSION}-linux-amd64.tar.gz",
            sha256="c7edd535941c48be6a362081a748272837de81ae11777202d9c341d3d8261c9a",
            member=f"pandoc-{PANDOC_VERSION}/bin/pandoc",
            binary="pandoc",
        ),
        "linux-arm64": Release(
            url=f"{_PANDOC_BASE}/pandoc-{PANDOC_VERSION}-linux-arm64.tar.gz",
            sha256="1c4d69f2a092bd47cb180e58a4aab7b9637101ced928252458c7d41a7f7fa71d",
            member=f"pandoc-{PANDOC_VERSION}/bin/pandoc",
            binary="pandoc",
        ),
        "windows-x86_64": Release(
            url=f"{_PANDOC_BASE}/pandoc-{PANDOC_VERSION}-windows-x86_64.zip",
            sha256="52487faaa63f8cef5363d5a771097da001228d61c6f44f32ed41b27a98c0278c",
            member=f"pandoc-{PANDOC_VERSION}/pandoc.exe",
            binary="pandoc.exe",
        ),
    },
    "typst": {
        "darwin-arm64": Release(
            url=f"{_TYPST_BASE}/typst-aarch64-apple-darwin.tar.xz",
            sha256="48f62ed034aa3a7978309579ac6ca00045e2ef0da73114e8af27cfd8e74dc05a",
            member="typst-aarch64-apple-darwin/typst",
            binary="typst",
        ),
        "darwin-x86_64": Release(
            url=f"{_TYPST_BASE}/typst-x86_64-apple-darwin.tar.xz",
            sha256="7f9fdd9584866245de9a79e0add8f9236fae6f40a8a45e2c4771ccc14db4e0fa",
            member="typst-x86_64-apple-darwin/typst",
            binary="typst",
        ),
        "linux-x86_64": Release(
            url=f"{_TYPST_BASE}/typst-x86_64-unknown-linux-musl.tar.xz",
            sha256="a6d077d0a95eed5a2eba715b2dae06be954f624ccbf85758a03f389ded33118c",
            member="typst-x86_64-unknown-linux-musl/typst",
            binary="typst",
        ),
        "linux-arm64": Release(
            url=f"{_TYPST_BASE}/typst-aarch64-unknown-linux-musl.tar.xz",
            sha256="5aa8d74a3d906e60ea12a66ac2f37f8eef1b14cbad7182a745e393a10c23dcee",
            member="typst-aarch64-unknown-linux-musl/typst",
            binary="typst",
        ),
        "windows-x86_64": Release(
            url=f"{_TYPST_BASE}/typst-x86_64-pc-windows-msvc.zip",
            sha256="19ce3551153c2fe7ee9fa2f95208310c8f4d3209fedb699e0333faf8913f6736",
            member="typst-x86_64-pc-windows-msvc/typst.exe",
            binary="typst.exe",
        ),
    },
}

# What Ora cannot do while a converter is missing, in the user's words.
_COSTS_WHEN_MISSING = {
    "pandoc": "Word (.docx) and PDF export stay unavailable",
    "typst": "PDF export stays unavailable",
}

_ARCH_ALIASES = {
    "x86_64": "x86_64",
    "amd64": "x86_64",
    "x64": "x86_64",
    "arm64": "arm64",
    "aarch64": "arm64",
    "aarch64_be": "arm64",
    "armv8b": "arm64",
    "armv8l": "arm64",
}


def platform_key(
    platform_name: str | None = None, machine: str | None = None
) -> str | None:
    """Name this machine the way ``RELEASES`` is keyed, or None if unpublished.

    None is a real answer, not a failure: neither publisher ships, say, a
    32-bit Linux build, and saying so is better than downloading the wrong one.
    """
    platform_name = (sys.platform if platform_name is None else platform_name).lower()
    machine = (platform.machine() if machine is None else machine).lower().strip()
    if platform_name.startswith("win"):
        system = "windows"
    elif platform_name.startswith("linux"):
        system = "linux"
    elif platform_name == "darwin":
        system = "darwin"
    else:
        return None
    arch = _ARCH_ALIASES.get(machine)
    if arch is None:
        return None
    if system == "windows":
        # Windows on ARM runs the x64 build through its own emulator.
        arch = "x86_64"
    return f"{system}-{arch}"


def _download(url: str) -> bytes:
    """Fetch one release archive, through Ora's validated public transport."""
    payload, _destination = network_policy.urllib_request_bytes(
        url,
        headers={"Accept": "application/octet-stream", "User-Agent": "ora-installer"},
        timeout=DOWNLOAD_TIMEOUT_SEC,
        max_bytes=MAX_ARCHIVE_BYTES,
    )
    return payload


def _verify_digest(payload: bytes, release: Release) -> None:
    """Refuse anything that is not byte-for-byte the pinned release."""
    actual = hashlib.sha256(payload).hexdigest()
    if actual != release.sha256:
        raise ConverterError(
            "REFUSED: the download does not match the checksum pinned in "
            f"scripts/converters.py.\n      expected sha256 {release.sha256}"
            f"\n      actual   sha256 {actual}"
            f"\n      source          {release.url}"
            "\n      Nothing was written to disk. Do not install this file by "
            "hand — either the release was re-cut upstream or the download was "
            "tampered with."
        )


def _extract_member(payload: bytes, release: Release) -> bytes:
    """Read exactly one named entry out of the archive, held in memory.

    The entry is addressed by its exact recorded name and the bytes are written
    to a destination this script chooses, so no archive can place a file
    anywhere of its own choosing.
    """
    buffer = io.BytesIO(payload)
    try:
        if release.url.endswith(".zip"):
            with zipfile.ZipFile(buffer) as archive:
                with archive.open(release.member) as handle:
                    return handle.read()
        with tarfile.open(fileobj=buffer, mode="r:*") as archive:
            handle = archive.extractfile(release.member)
            if handle is None:
                raise ConverterError(
                    f"{release.member} is not a file inside {release.url}"
                )
            with handle:
                return handle.read()
    except (KeyError, OSError, tarfile.TarError, zipfile.BadZipFile) as exc:
        raise ConverterError(
            f"could not read {release.member} out of the archive: {exc}"
        ) from exc


def _install_binary(data: bytes, target: Path) -> None:
    """Write the program, then move it into place in one step."""
    target.parent.mkdir(parents=True, exist_ok=True)
    staged = target.with_name(target.name + ".part")
    try:
        with open(staged, "wb") as handle:
            handle.write(data)
        if os.name != "nt":
            os.chmod(staged, 0o755)
        os.replace(staged, target)
    except OSError as exc:
        try:
            staged.unlink()
        except OSError:
            pass
        raise ConverterError(f"could not write {target}: {exc}") from exc


def _discard(path: Path) -> None:
    """Take back a program that failed its post-unpack run.

    A file that downloaded cleanly but will not execute is worse than no file
    at all: the very next run finds it, reports ``already on this machine``,
    and Ora turns the Word and PDF buttons on over a converter that produces
    nothing. Leaving nothing behind keeps the honest answer — unavailable —
    and makes the printed retry command actually re-download.

    The two directories this script creates go too — ``converters/bin`` and
    ``converters/`` — but only while they are empty, and the walk stops at the
    first one that is not. A converter provisioned successfully earlier in the
    same run is still sitting in there, and ``rmdir`` will not touch it.
    """
    try:
        path.unlink()
    except OSError:
        return
    for directory in (path.parent, path.parent.parent):
        try:
            directory.rmdir()
        except OSError:
            break


def _verify_runs(path: Path, tool: str) -> str:
    """Run the program once. An unpacked file that will not run is a failure.

    Raising always removes ``path`` — see ``_discard``.
    """
    try:
        try:
            proc = subprocess.run(
                [str(path), "--version"],
                capture_output=True,
                text=True,
                timeout=VERIFY_TIMEOUT_SEC,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise ConverterError(f"{path} would not run: {exc}") from exc
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "").strip().splitlines()
            raise ConverterError(
                f"{path} --version exited {proc.returncode}: "
                f"{detail[-1] if detail else 'no output'}"
            )
        lines = (proc.stdout or "").strip().splitlines()
        banner = lines[0].strip() if lines else ""
        if tool not in banner.lower():
            raise ConverterError(
                f"{path} --version did not identify itself as {tool}: {banner!r}"
            )
    except BaseException:
        # Every way out of the check that is not a banner leaves the machine
        # as it was before the download: no half-working converter, and no
        # directory entry for the next run to mistake for a good one.
        _discard(path)
        raise
    return banner


def provision(
    tool: str, *, force: bool = False, dry_run: bool = False, log=print
) -> Result:
    """Make one converter available, or explain exactly why it is not."""
    cost = _COSTS_WHEN_MISSING.get(tool, "some export formats stay unavailable")
    existing = export._which(tool)
    if existing and not force:
        log(f"  ✓ {tool} already on this machine: {existing}")
        log("    Nothing downloaded — Ora will use the copy you already have.")
        return Result(tool, "present", f"already installed at {existing}", existing)

    key = platform_key()
    release = RELEASES.get(tool, {}).get(key or "")
    if release is None:
        detail = (
            f"no official {tool} release is published for "
            f"{sys.platform}/{platform.machine()}"
        )
        log(f"  ✗ {tool}: {detail}")
        log(f"    {cost}. Install {tool} yourself if you need it.")
        return Result(tool, "failed", detail)

    target = export.converters_dir() / release.binary
    if dry_run:
        log(f"  [dry-run] would download {release.url}")
        log(f"  [dry-run] would verify sha256 {release.sha256}")
        log(f"  [dry-run] would install {target}")
        return Result(tool, "would-install", f"would install {target}", str(target))

    log(f"  · downloading {tool} {release.url.rsplit('/', 1)[-1]}")
    try:
        payload = _download(release.url)
        _verify_digest(payload, release)
        log(f"    checksum verified (sha256 {release.sha256[:16]}…)")
        _install_binary(_extract_member(payload, release), target)
        banner = _verify_runs(target, tool)
    except ConverterError as exc:
        log(f"  ✗ {tool}: {exc}")
        log(f"    {cost}. Retry with: {RETRY_COMMAND}")
        return Result(tool, "failed", str(exc))
    except Exception as exc:  # network / transport / anything else
        log(f"  ✗ {tool}: download failed — {type(exc).__name__}: {exc}")
        log(f"    {cost}. Retry with: {RETRY_COMMAND}")
        return Result(tool, "failed", f"{type(exc).__name__}: {exc}")

    log(f"  ✓ {tool} installed: {target}")
    log(f"    {banner}")
    return Result(tool, "installed", banner, str(target))


def provision_all(*, force: bool = False, dry_run: bool = False, log=print) -> list[Result]:
    """Pandoc first — Typst is only useful once Pandoc can drive it."""
    return [
        provision(tool, force=force, dry_run=dry_run, log=log)
        for tool in ("pandoc", "typst")
    ]


def summarize(results: list[Result], log=print) -> bool:
    """Say plainly which export formats the user now has. True = all good."""
    failed = [r for r in results if not r.ok]
    if not failed:
        if any(r.status == "would-install" for r in results):
            log("  · Nothing was changed. Re-run without --dry-run to install.")
        else:
            log("  ✓ Word (.docx) and PDF export are ready.")
        return True
    names = " and ".join(r.tool for r in failed)
    log(f"  ⚠ {names} could not be provisioned.")
    log("    Saving to the vault as Markdown and printing still work; only the")
    log("    Word and PDF render targets are affected.")
    log(f"    Retry with: {RETRY_COMMAND}")
    return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Download Pandoc + Typst so Ora can export Word and PDF.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Report what would happen; change nothing.",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Fetch Ora's own copy even when the machine already has one.",
    )
    args = parser.parse_args(argv)

    print(f"Converters for Word/PDF export → {export.converters_dir()}")
    results = provision_all(force=args.force, dry_run=args.dry_run)
    return 0 if summarize(results) else 1


if __name__ == "__main__":
    sys.exit(main())
