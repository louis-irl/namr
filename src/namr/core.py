# SPDX-License-Identifier: Unlicense
"""Core rename engine, rule protocol, conflict validation, and safe execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import html
import os
from pathlib import Path
import sys
from typing import Iterable, Protocol, runtime_checkable


class ItemStatus(str, Enum):
    """Status of an item in the rename preview."""

    UNCHANGED = "unchanged"
    READY = "ready"
    CONFLICT = "conflict"
    INVALID = "invalid"
    RENAMED = "renamed"
    ERROR = "error"


class TargetScope(str, Enum):
    """Which items a rename operation should apply to."""

    BOTH = "both"
    FILES_ONLY = "files_only"
    DIRS_ONLY = "dirs_only"


@dataclass
class RenameItem:
    """Represents a single file or directory loaded into the renamer."""

    source_path: Path
    is_dir: bool
    enabled: bool = True
    collapsed: bool = False
    new_name: str = ""
    source_diff_html: str = ""
    diff_html: str = ""
    status: ItemStatus = ItemStatus.UNCHANGED
    error_message: str = ""
    _already_resolved: bool = field(default=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if not self._already_resolved:
            self.source_path = Path(self.source_path).resolve()
        escaped = html.escape(self.original_name)
        if not self.new_name:
            self.new_name = self.original_name
        if not self.source_diff_html:
            self.source_diff_html = escaped
        if not self.diff_html:
            self.diff_html = escaped

    @property
    def original_name(self) -> str:
        return self.source_path.name

    @property
    def parent_dir(self) -> Path:
        return self.source_path.parent

    @property
    def target_path(self) -> Path:
        return self.parent_dir / self.new_name

    @property
    def depth(self) -> int:
        return len(self.source_path.parts)


@runtime_checkable
class RenameRule(Protocol):
    """Protocol for all rename rules (Find & Replace, Regex, Numbering, Case, etc.)."""

    def compute_new_name(self, original_name: str, is_dir: bool, index: int = 0) -> str:
        """Compute the new filename for an item."""
        ...

    def compute_source_diff_html(self, original_name: str, is_dir: bool, index: int = 0) -> str:
        """Compute rich HTML string highlighting matched text in the original name."""
        ...

    def compute_diff_html(self, original_name: str, is_dir: bool, index: int = 0) -> str:
        """Compute rich HTML string highlighting the changes in the new name."""
        ...

    def evaluate_item(self, original_name: str, is_dir: bool, index: int = 0) -> tuple[str, str, str]:
        """Compute (new_name, source_diff_html, target_diff_html) in a single pass."""
        ...


def _split_stem_and_ext(name: str, is_dir: bool, include_extension: bool) -> tuple[str, str]:
    """Split a filename into (editable_part, preserved_extension)."""
    if is_dir or include_extension:
        return name, ""
    # Hidden files like ".bashrc" have no extension in pathlib stem/suffix terms
    if name.startswith(".") and "." not in name[1:]:
        return name, ""
    dot_idx = name.rfind(".")
    if dot_idx <= 0:
        return name, ""
    return name[:dot_idx], name[dot_idx:]


@dataclass
class FindReplaceRule:
    """Find and replace text in file or directory names."""

    find_text: str = ""
    replace_text: str = ""
    case_sensitive: bool = True
    include_extension: bool = False
    target_scope: TargetScope = TargetScope.BOTH

    def applies_to(self, is_dir: bool) -> bool:
        if self.target_scope == TargetScope.FILES_ONLY and is_dir:
            return False
        if self.target_scope == TargetScope.DIRS_ONLY and not is_dir:
            return False
        return True

    def _find_matches(self, text: str) -> list[tuple[int, int]]:
        """Return non-overlapping (start, end) spans where find_text matches."""
        if not self.find_text:
            return []
        haystack = text if self.case_sensitive else text.lower()
        needle = self.find_text if self.case_sensitive else self.find_text.lower()
        spans: list[tuple[int, int]] = []
        start = 0
        needle_len = len(needle)
        while True:
            idx = haystack.find(needle, start)
            if idx == -1:
                break
            spans.append((idx, idx + needle_len))
            start = idx + needle_len
        return spans

    def evaluate_item(self, original_name: str, is_dir: bool, index: int = 0) -> tuple[str, str, str]:
        """Compute (new_name, source_diff_html, target_diff_html) in a single pass."""
        if not self.find_text or not self.applies_to(is_dir):
            escaped = html.escape(original_name)
            return original_name, escaped, escaped

        editable, ext = _split_stem_and_ext(
            original_name, is_dir, self.include_extension
        )
        spans = self._find_matches(editable)
        if not spans:
            escaped = html.escape(original_name)
            return original_name, escaped, escaped

        new_parts: list[str] = []
        src_parts: list[str] = []
        dst_parts: list[str] = []
        escaped_replace = html.escape(self.replace_text)
        last_idx = 0

        for start, end in spans:
            prefix = editable[last_idx:start]
            escaped_prefix = html.escape(prefix)
            matched = html.escape(editable[start:end])

            new_parts.append(prefix)
            new_parts.append(self.replace_text)
            src_parts.append(escaped_prefix)
            dst_parts.append(escaped_prefix)

            if self.replace_text:
                src_parts.append(f"<b><font color='#f39c12'>{matched}</font></b>")
                dst_parts.append(f"<b><font color='#2ecc71'>{escaped_replace}</font></b>")
            else:
                strike = f"<s><font color='#e74c3c'>{matched}</font></s>"
                src_parts.append(strike)
                dst_parts.append(strike)

            last_idx = end

        suffix = editable[last_idx:]
        escaped_tail = html.escape(suffix) + html.escape(ext)
        new_name = "".join(new_parts) + suffix + ext
        src_html = "".join(src_parts) + escaped_tail
        dst_html = "".join(dst_parts) + escaped_tail
        return new_name, src_html, dst_html

    def compute_new_name(self, original_name: str, is_dir: bool, index: int = 0) -> str:
        return self.evaluate_item(original_name, is_dir, index)[0]

    def compute_source_diff_html(self, original_name: str, is_dir: bool, index: int = 0) -> str:
        return self.evaluate_item(original_name, is_dir, index)[1]

    def compute_diff_html(self, original_name: str, is_dir: bool, index: int = 0) -> str:
        return self.evaluate_item(original_name, is_dir, index)[2]


# Cross-platform filename validation constants
WINDOWS_RESERVED_CHARS = frozenset('<>:"/\\|?*')
WINDOWS_RESERVED_NAMES = frozenset(
    {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{i}" for i in range(1, 10)),
        *(f"LPT{i}" for i in range(1, 10)),
    }
)


def validate_filename(name: str, strict_cross_platform: bool = True) -> str | None:
    """Validate a candidate filename.

    Returns an error string if invalid, or None if valid.
    """
    if not name or not name.strip():
        return "Name cannot be empty"
    if name in {".", ".."}:
        return f"Reserved name: '{name}'"
    if "/" in name or "\x00" in name:
        return "Invalid character: /"

    check_windows = strict_cross_platform or sys.platform.startswith("win")
    if check_windows:
        bad_chars = [ch for ch in name if ch in WINDOWS_RESERVED_CHARS]
        if bad_chars:
            return f"Invalid character: {' '.join(sorted(set(bad_chars)))}"
        if name.endswith(" ") or name.endswith("."):
            return "Cannot end with space or dot"
        stem = name.split(".")[0].upper()
        if stem in WINDOWS_RESERVED_NAMES:
            return f"Reserved name: {stem}"

    return None


@dataclass
class BatchRecord:
    """Stores a completed batch of renames so it can be undone."""

    # List of (source_path_before_rename, target_path_after_rename) in execution order
    operations: list[tuple[Path, Path]] = field(default_factory=list)


@dataclass
class BatchResult:
    """Result of executing or undoing a batch rename."""

    success_count: int = 0
    errors: list[tuple[Path, str]] = field(default_factory=list)
    record: BatchRecord | None = None

    @property
    def ok(self) -> bool:
        return len(self.errors) == 0


def collect_paths(
    inputs: Iterable[str | Path],
    recursive: bool = True,
    include_hidden: bool = False,
) -> list[tuple[Path, bool]]:
    """Collect and deduplicate files and directories from input paths."""
    seen: set[Path] = set()
    results: list[tuple[Path, bool]] = []

    def _add(p: Path, is_dir: bool | None = None) -> Path | None:
        try:
            resolved = p.resolve()
        except OSError:
            return None
        if resolved in seen:
            return None
        if is_dir is None:
            if not resolved.exists():
                return None
            is_dir = resolved.is_dir()
        seen.add(resolved)
        results.append((resolved, is_dir))
        return resolved

    for raw in inputs:
        path = Path(raw)
        if not path.exists():
            continue
        is_dir = path.is_dir()
        resolved_root = _add(path, is_dir=is_dir)
        if recursive and is_dir and resolved_root is not None:
            for root, dirs, files in os.walk(resolved_root):
                root_path = Path(root)
                if not include_hidden:
                    dirs[:] = [d for d in dirs if not d.startswith(".")]
                    files = [f for f in files if not f.startswith(".")]
                dirs.sort()
                files.sort()
                for d in dirs:
                    _add(root_path / d, is_dir=True)
                for f in files:
                    _add(root_path / f, is_dir=False)

    return results


def evaluate_preview(
    items: list[RenameItem],
    rule: RenameRule,
    strict_cross_platform: bool = True,
) -> None:
    """Update new_name, diff_html, status, and error_message on all items in-place."""
    # First pass: compute candidate names and validate syntax
    target_counts: dict[Path, int] = {}
    source_set: set[Path] = {item.source_path for item in items}
    has_fast_eval = hasattr(rule, "evaluate_item")

    for idx, item in enumerate(items):
        if not item.enabled:
            escaped = html.escape(item.original_name)
            item.new_name = item.original_name
            item.source_diff_html = escaped
            item.diff_html = escaped
            item.status = ItemStatus.UNCHANGED
            item.error_message = ""
            target_counts[item.source_path] = target_counts.get(item.source_path, 0) + 1
            continue

        if has_fast_eval:
            item.new_name, item.source_diff_html, item.diff_html = rule.evaluate_item(
                item.original_name, item.is_dir, idx
            )
        else:
            item.new_name = rule.compute_new_name(item.original_name, item.is_dir, idx)
            item.source_diff_html = rule.compute_source_diff_html(
                item.original_name, item.is_dir, idx
            )
            item.diff_html = rule.compute_diff_html(item.original_name, item.is_dir, idx)

        validation_err = validate_filename(
            item.new_name, strict_cross_platform=strict_cross_platform
        )
        if validation_err:
            item.status = ItemStatus.INVALID
            item.error_message = validation_err
            # Colour invalid replacement in red instead of green
            item.diff_html = item.diff_html.replace("#2ecc71", "#e74c3c")
            continue

        if item.new_name == item.original_name:
            item.status = ItemStatus.UNCHANGED
            item.error_message = ""
        else:
            item.status = ItemStatus.READY
            item.error_message = ""

        target_counts[item.target_path] = target_counts.get(item.target_path, 0) + 1

    # Second pass: check for duplicate targets within batch or existing files on disk
    for item in items:
        if item.status in (ItemStatus.INVALID, ItemStatus.UNCHANGED) and (
            target_counts.get(item.target_path, 0) <= 1
        ):
            continue

        target = item.target_path
        if target_counts.get(target, 0) > 1:
            item.status = ItemStatus.CONFLICT
            item.error_message = "Duplicate target name"
        elif (
            item.status == ItemStatus.READY
            and target not in source_set
            and target.exists()
        ):
            item.status = ItemStatus.CONFLICT
            item.error_message = "File already exists on disk"


def execute_batch(items: list[RenameItem]) -> BatchResult:
    """Safely execute renames for all READY items, deepest paths first.

    Uses a two-phase temporary path swap when items in the batch rename onto
    each other's original paths (e.g. A -> B and B -> C), and sorts by
    descending path depth so children are renamed before their parent directories.
    """
    ready_items = [item for item in items if item.enabled and item.status == ItemStatus.READY]
    if not ready_items:
        return BatchResult(success_count=0)

    # Abort if any enabled item has a conflict or invalid name
    blocking = [
        item
        for item in items
        if item.enabled and item.status in (ItemStatus.CONFLICT, ItemStatus.INVALID)
    ]
    if blocking:
        return BatchResult(
            success_count=0,
            errors=[(b.source_path, b.error_message or "Conflict detected") for b in blocking],
        )

    # Sort deepest paths first so renaming a directory doesn't invalidate child paths
    ordered = sorted(ready_items, key=lambda x: x.depth, reverse=True)

    result = BatchResult(record=BatchRecord())
    source_paths = {item.source_path for item in ordered}

    temp_map: list[tuple[RenameItem, Path, Path, Path]] = []
    errors: list[tuple[Path, str]] = []

    # Phase 1: move any item that participates in a source/target overlap to a unique temp path
    target_paths = {item.target_path for item in ordered}
    overlap_paths = source_paths & target_paths
    for idx, item in enumerate(ordered):
        src = item.source_path
        dst = item.target_path
        if (src in overlap_paths or dst in overlap_paths) and src.parent == dst.parent:
            tmp = src.parent / f".namr_tmp_{os.getpid()}_{idx}_{src.name}"
            try:
                src.rename(tmp)
                temp_map.append((item, src, tmp, dst))
            except OSError as exc:
                item.status = ItemStatus.ERROR
                item.error_message = str(exc)
                errors.append((src, str(exc)))
        else:
            temp_map.append((item, src, src, dst))

    if errors:
        # Roll back any temp renames we already did
        for _item, orig_src, cur_path, _dst in reversed(temp_map):
            if cur_path != orig_src and cur_path.exists():
                try:
                    cur_path.rename(orig_src)
                except OSError:
                    pass
        result.errors = errors
        return result

    # Phase 2: move to final destination and update in-memory paths (including child paths if a parent dir renamed)
    dir_renames: list[tuple[Path, Path]] = []

    for item, orig_src, cur_path, dst in temp_map:
        try:
            cur_path.rename(dst)
            if result.record is not None:
                result.record.operations.append((orig_src, dst))
            escaped = html.escape(dst.name)
            item.source_path = dst
            item.new_name = dst.name
            item.source_diff_html = escaped
            item.diff_html = escaped
            item.status = ItemStatus.RENAMED
            item.error_message = ""
            result.success_count += 1
            if item.is_dir:
                dir_renames.append((orig_src, dst))
        except OSError as exc:
            item.status = ItemStatus.ERROR
            item.error_message = str(exc)
            result.errors.append((orig_src, str(exc)))

    # If any directories were renamed, update source_path of descendant items in `items`
    if dir_renames:
        for item in items:
            for old_dir, new_dir in dir_renames:
                if item.source_path != new_dir and old_dir in item.source_path.parents:
                    rel = item.source_path.relative_to(old_dir)
                    item.source_path = new_dir / rel

    return result


def undo_batch(record: BatchRecord, items: list[RenameItem] | None = None) -> BatchResult:
    """Undo a previously executed BatchRecord in reverse order."""
    result = BatchResult()
    if not record.operations:
        return result

    # Reverse the execution order (parents were renamed after children, so undo renames parents first!)
    dir_rewrites: list[tuple[Path, Path]] = []

    for orig_src, dst in reversed(record.operations):
        # Account for any parent directory that was already reverted in an earlier iteration
        actual_dst = dst
        actual_orig = orig_src
        for prev_dst_dir, prev_orig_dir in dir_rewrites:
            if prev_dst_dir in actual_dst.parents:
                actual_dst = prev_orig_dir / actual_dst.relative_to(prev_dst_dir)
            if prev_dst_dir in actual_orig.parents:
                actual_orig = prev_orig_dir / actual_orig.relative_to(prev_dst_dir)

        try:
            is_dir = actual_dst.is_dir()
            actual_dst.rename(actual_orig)
            result.success_count += 1
            if is_dir:
                dir_rewrites.append((actual_dst, actual_orig))
        except OSError as exc:
            result.errors.append((actual_dst, str(exc)))

    if items is not None:
        # Refresh item source_paths that matched reverted operations
        revert_map = {dst: orig_src for orig_src, dst in record.operations}
        for item in items:
            for dst_dir, orig_dir in dir_rewrites:
                if dst_dir in item.source_path.parents:
                    item.source_path = orig_dir / item.source_path.relative_to(dst_dir)
            if item.source_path in revert_map:
                item.source_path = revert_map[item.source_path]

    return result

