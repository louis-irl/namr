# SPDX-License-Identifier: Unlicense
"""Qt6 / QML models and controller for Namr."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import (
    Property,
    QAbstractListModel,
    QByteArray,
    QMimeDatabase,
    QModelIndex,
    QObject,
    Qt,
    QUrl,
    Signal,
    Slot,
)

from namr import __version__
from namr.core import (
    BatchRecord,
    FindReplaceRule,
    ItemStatus,
    RenameItem,
    TargetScope,
    collect_paths,
    evaluate_preview,
    execute_batch,
    undo_batch,
)


class RenameItemModel(QAbstractListModel):
    """Collapsible hierarchical tree model exposing RenameItem entries to QML."""

    OriginalNameRole = Qt.ItemDataRole.UserRole + 1
    NewNameRole = Qt.ItemDataRole.UserRole + 2
    DiffHtmlRole = Qt.ItemDataRole.UserRole + 3
    ParentDirRole = Qt.ItemDataRole.UserRole + 4
    SourcePathRole = Qt.ItemDataRole.UserRole + 5
    IsDirRole = Qt.ItemDataRole.UserRole + 6
    EnabledRole = Qt.ItemDataRole.UserRole + 7
    StatusRole = Qt.ItemDataRole.UserRole + 8
    ErrorMessageRole = Qt.ItemDataRole.UserRole + 9
    IndentLevelRole = Qt.ItemDataRole.UserRole + 10
    HasChildrenRole = Qt.ItemDataRole.UserRole + 11
    IsExpandedRole = Qt.ItemDataRole.UserRole + 12
    ShowParentDirRole = Qt.ItemDataRole.UserRole + 13
    IconNameRole = Qt.ItemDataRole.UserRole + 14
    SourceDiffHtmlRole = Qt.ItemDataRole.UserRole + 15

    _ROLE_NAMES: dict[int, QByteArray] = {
        OriginalNameRole: QByteArray(b"originalName"),
        NewNameRole: QByteArray(b"newName"),
        DiffHtmlRole: QByteArray(b"diffHtml"),
        ParentDirRole: QByteArray(b"parentDir"),
        SourcePathRole: QByteArray(b"sourcePath"),
        IsDirRole: QByteArray(b"isDir"),
        EnabledRole: QByteArray(b"itemEnabled"),
        StatusRole: QByteArray(b"status"),
        ErrorMessageRole: QByteArray(b"errorMessage"),
        IndentLevelRole: QByteArray(b"indentLevel"),
        HasChildrenRole: QByteArray(b"hasChildren"),
        IsExpandedRole: QByteArray(b"isExpanded"),
        ShowParentDirRole: QByteArray(b"showParentDir"),
        IconNameRole: QByteArray(b"iconName"),
        SourceDiffHtmlRole: QByteArray(b"sourceDiffHtml"),
    }

    _UPDATED_ROLES: list[int] = [
        OriginalNameRole,
        NewNameRole,
        DiffHtmlRole,
        ParentDirRole,
        SourcePathRole,
        EnabledRole,
        StatusRole,
        ErrorMessageRole,
        IndentLevelRole,
        HasChildrenRole,
        IsExpandedRole,
        ShowParentDirRole,
        IconNameRole,
        SourceDiffHtmlRole,
    ]

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._all_items: list[RenameItem] = []
        self._visible_items: list[RenameItem] = []
        self._children_map: dict[Path, list[RenameItem]] = {}
        self._indent_map: dict[Path, int] = {}
        self._has_parent_in_set: set[Path] = set()
        self._multiple_root_parents: bool = False
        self._changed_only: bool = False
        self._mime_db = QMimeDatabase()
        self._icon_cache: dict[str, str] = {}

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._visible_items)

    def roleNames(self) -> dict[int, QByteArray]:
        return self._ROLE_NAMES

    def _icon_for_item(self, item: RenameItem) -> str:
        if item.is_dir:
            if self._children_map.get(item.source_path) and not item.collapsed:
                return "folder-open"
            return "folder"
        ext = item.source_path.suffix.lower()
        if ext and ext in self._icon_cache:
            return self._icon_cache[ext]
        mime = self._mime_db.mimeTypeForFile(
            str(item.source_path), QMimeDatabase.MatchMode.MatchExtension
        )
        icon_name = mime.iconName() or mime.genericIconName() or "text-x-generic"
        if ext:
            self._icon_cache[ext] = icon_name
        return icon_name

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid() or not (0 <= index.row() < len(self._visible_items)):
            return None
        item = self._visible_items[index.row()]
        path = item.source_path
        if role == self.OriginalNameRole:
            return item.original_name
        if role == self.NewNameRole:
            return item.new_name
        if role == self.DiffHtmlRole:
            return item.diff_html
        if role == self.ParentDirRole:
            return item.parent_dir.name or str(item.parent_dir)
        if role == self.SourcePathRole:
            return str(path)
        if role == self.IsDirRole:
            return item.is_dir
        if role == self.EnabledRole:
            return item.enabled
        if role == self.StatusRole:
            return item.status.value
        if role == self.ErrorMessageRole:
            return item.error_message
        if role == self.IndentLevelRole:
            return self._indent_map.get(path, 0)
        if role == self.HasChildrenRole:
            return bool(self._children_map.get(path))
        if role == self.IsExpandedRole:
            return not item.collapsed
        if role == self.ShowParentDirRole:
            return self._multiple_root_parents and (path not in self._has_parent_in_set)
        if role == self.IconNameRole:
            return self._icon_for_item(item)
        if role == self.SourceDiffHtmlRole:
            return item.source_diff_html
        return None

    @property
    def items(self) -> list[RenameItem]:
        return self._all_items

    @property
    def changed_only(self) -> bool:
        return self._changed_only

    def _rebuild_tree(self) -> None:
        """Rebuild the hierarchical ordering, indentation levels, and visible rows."""
        self.beginResetModel()
        path_map = {item.source_path: item for item in self._all_items}
        self._children_map = {item.source_path: [] for item in self._all_items}
        self._has_parent_in_set.clear()
        self._indent_map.clear()

        roots: list[RenameItem] = []

        for item in self._all_items:
            # Find nearest ancestor present in the loaded items
            parent_item: RenameItem | None = None
            curr = item.source_path.parent
            while curr != curr.parent:
                if curr in path_map:
                    parent_item = path_map[curr]
                    break
                curr = curr.parent

            if parent_item is not None:
                self._children_map[parent_item.source_path].append(item)
                self._has_parent_in_set.add(item.source_path)
            else:
                roots.append(item)

        # Sort siblings: directories first, then alphabetically by original name
        def _sort_key(it: RenameItem) -> tuple[int, str]:
            return (0 if it.is_dir else 1, it.original_name.lower())

        roots.sort(key=_sort_key)
        self._multiple_root_parents = len({r.parent_dir for r in roots}) > 1
        for children in self._children_map.values():
            children.sort(key=_sort_key)

        # Depth-first traversal to build full ordered list and visible list
        ordered_all: list[RenameItem] = []
        visible: list[RenameItem] = []

        # If filtering to changed/conflicted items only, determine which nodes (and their ancestors) match
        active_set: set[Path] = set()
        if self._changed_only:
            for it in self._all_items:
                if it.status != ItemStatus.UNCHANGED:
                    active_set.add(it.source_path)
                    curr = it.source_path.parent
                    while curr != curr.parent and curr not in active_set:
                        if curr in path_map:
                            active_set.add(curr)
                        curr = curr.parent

        def _visit(node: RenameItem, level: int, ancestor_collapsed: bool) -> None:
            ordered_all.append(node)
            self._indent_map[node.source_path] = level
            if not ancestor_collapsed and (
                not self._changed_only or node.source_path in active_set
            ):
                visible.append(node)
            is_collapsed = ancestor_collapsed or node.collapsed
            for child in self._children_map.get(node.source_path, []):
                _visit(child, level + 1, is_collapsed)

        for root_item in roots:
            _visit(root_item, 0, False)

        self._all_items = ordered_all
        self._visible_items = visible
        self.endResetModel()

    def add_items(self, new_entries: list[tuple[Path, bool]]) -> int:
        existing = {item.source_path for item in self._all_items}
        to_add = [
            RenameItem(source_path=p, is_dir=is_dir, _already_resolved=True)
            for p, is_dir in new_entries
            if p not in existing
        ]
        if not to_add:
            return 0
        self._all_items.extend(to_add)
        self._rebuild_tree()
        return len(to_add)

    def remove_at(self, visible_row: int) -> None:
        if not (0 <= visible_row < len(self._visible_items)):
            return
        target = self._visible_items[visible_row]
        target_path = target.source_path
        if target.is_dir:
            # Also remove all descendants in the tree
            self._all_items = [
                item
                for item in self._all_items
                if not item.source_path.is_relative_to(target_path)
            ]
        else:
            self._all_items = [
                item for item in self._all_items if item.source_path != target_path
            ]
        self._rebuild_tree()

    def clear(self) -> None:
        if not self._all_items:
            return
        self.beginResetModel()
        self._all_items.clear()
        self._visible_items.clear()
        self._children_map.clear()
        self._indent_map.clear()
        self._has_parent_in_set.clear()
        self._multiple_root_parents = False
        self.endResetModel()

    def toggle_expanded(self, visible_row: int) -> None:
        if not (0 <= visible_row < len(self._visible_items)):
            return
        item = self._visible_items[visible_row]
        if not self._children_map.get(item.source_path):
            return
        item.collapsed = not item.collapsed
        self._rebuild_tree()

    def set_item_enabled(self, visible_row: int, enabled: bool) -> None:
        if not (0 <= visible_row < len(self._visible_items)):
            return
        target = self._visible_items[visible_row]
        target_path = target.source_path
        changed = False
        if target.is_dir:
            # When toggling a folder checkbox, also toggle its descendants for convenience
            for item in self._all_items:
                if item.source_path.is_relative_to(target_path) and item.enabled != enabled:
                    item.enabled = enabled
                    changed = True
        elif target.enabled != enabled:
            target.enabled = enabled
            changed = True
        if changed:
            self.notify_all_updated()

    def set_changed_only(self, value: bool) -> None:
        if self._changed_only != value:
            self._changed_only = value
            self._rebuild_tree()

    def refresh_after_evaluate(self) -> None:
        """Refresh model rows after rule evaluation."""
        if self._changed_only:
            self._rebuild_tree()
        else:
            self.notify_all_updated()

    def rebuild_after_path_changes(self) -> None:
        """Call after batch execute or undo when item source_paths have changed."""
        self._rebuild_tree()

    def notify_all_updated(self) -> None:
        if not self._visible_items:
            return
        top = self.index(0, 0)
        bottom = self.index(len(self._visible_items) - 1, 0)
        self.dataChanged.emit(top, bottom, self._UPDATED_ROLES)


class RenamerController(QObject):
    """Main QML-accessible controller coordinating rule state, preview, and execution."""

    ruleChanged = Signal()
    statsChanged = Signal()
    historyChanged = Signal()
    notificationRequested = Signal(str, str)  # (message, type: "positive" | "warning" | "error")

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._model = RenameItemModel(self)
        self._rule = FindReplaceRule()
        self._recursive = True
        self._include_hidden = False
        self._strict_cross_platform = True
        self._undo_stack: list[BatchRecord] = []
        self._total_count = 0
        self._ready_count = 0
        self._conflict_count = 0
        self._all_check_state = int(Qt.CheckState.Unchecked.value)

    @Property(QObject, constant=True)
    def itemModel(self) -> RenameItemModel:
        return self._model

    @Property(str, constant=True)
    def appVersion(self) -> str:
        return __version__

    # --- Rule properties ---

    def _get_find_text(self) -> str:
        return self._rule.find_text

    def _set_find_text(self, value: str) -> None:
        if self._rule.find_text != value:
            self._rule.find_text = value
            self.ruleChanged.emit()
            self._recalculate()

    findText = Property(str, _get_find_text, _set_find_text, notify=ruleChanged)

    def _get_replace_text(self) -> str:
        return self._rule.replace_text

    def _set_replace_text(self, value: str) -> None:
        if self._rule.replace_text != value:
            self._rule.replace_text = value
            self.ruleChanged.emit()
            self._recalculate()

    replaceText = Property(
        str, _get_replace_text, _set_replace_text, notify=ruleChanged
    )

    def _get_case_sensitive(self) -> bool:
        return self._rule.case_sensitive

    def _set_case_sensitive(self, value: bool) -> None:
        if self._rule.case_sensitive != value:
            self._rule.case_sensitive = value
            self.ruleChanged.emit()
            self._recalculate()

    caseSensitive = Property(
        bool, _get_case_sensitive, _set_case_sensitive, notify=ruleChanged
    )

    def _get_include_extension(self) -> bool:
        return self._rule.include_extension

    def _set_include_extension(self, value: bool) -> None:
        if self._rule.include_extension != value:
            self._rule.include_extension = value
            self.ruleChanged.emit()
            self._recalculate()

    includeExtension = Property(
        bool, _get_include_extension, _set_include_extension, notify=ruleChanged
    )

    def _get_target_scope(self) -> str:
        return self._rule.target_scope.value

    def _set_target_scope(self, value: str) -> None:
        try:
            scope = TargetScope(value)
        except ValueError:
            return
        if self._rule.target_scope != scope:
            self._rule.target_scope = scope
            self.ruleChanged.emit()
            self._recalculate()

    targetScope = Property(
        str, _get_target_scope, _set_target_scope, notify=ruleChanged
    )

    def _get_recursive_scan(self) -> bool:
        return self._recursive

    def _set_recursive_scan(self, value: bool) -> None:
        if self._recursive != value:
            self._recursive = value
            self.ruleChanged.emit()
            if value and self._model.items:
                dir_paths = [
                    str(item.source_path)
                    for item in self._model.items
                    if item.is_dir
                ]
                if dir_paths:
                    self.addPaths(dir_paths)

    recursiveScan = Property(
        bool, _get_recursive_scan, _set_recursive_scan, notify=ruleChanged
    )

    def _get_strict_cross_platform(self) -> bool:
        return self._strict_cross_platform

    def _set_strict_cross_platform(self, value: bool) -> None:
        if self._strict_cross_platform != value:
            self._strict_cross_platform = value
            self.ruleChanged.emit()
            self._recalculate()

    strictCrossPlatform = Property(
        bool,
        _get_strict_cross_platform,
        _set_strict_cross_platform,
        notify=ruleChanged,
    )

    def _get_show_changed_only(self) -> bool:
        return self._model.changed_only

    def _set_show_changed_only(self, value: bool) -> None:
        if self._model.changed_only != value:
            self._model.set_changed_only(value)
            self.ruleChanged.emit()

    showChangedOnly = Property(
        bool, _get_show_changed_only, _set_show_changed_only, notify=ruleChanged
    )

    # --- Summary statistics ---

    @Property(int, notify=statsChanged)
    def allCheckState(self) -> int:
        return self._all_check_state

    @Property(int, notify=statsChanged)
    def totalCount(self) -> int:
        return self._total_count

    @Property(int, notify=statsChanged)
    def readyCount(self) -> int:
        return self._ready_count

    @Property(int, notify=statsChanged)
    def conflictCount(self) -> int:
        return self._conflict_count

    @Property(bool, notify=statsChanged)
    def canRename(self) -> bool:
        return self._ready_count > 0 and self._conflict_count == 0

    @Property(bool, notify=historyChanged)
    def canUndo(self) -> bool:
        return len(self._undo_stack) > 0

    def _update_stats(self) -> None:
        items = self._model.items
        total = len(items)
        enabled_count = 0
        ready = 0
        conflicts = 0
        for item in items:
            if item.enabled:
                enabled_count += 1
                if item.status == ItemStatus.READY:
                    ready += 1
                elif item.status in (ItemStatus.CONFLICT, ItemStatus.INVALID):
                    conflicts += 1

        self._total_count = total
        self._ready_count = ready
        self._conflict_count = conflicts
        if total == 0 or enabled_count == 0:
            self._all_check_state = int(Qt.CheckState.Unchecked.value)
        elif enabled_count == total:
            self._all_check_state = int(Qt.CheckState.Checked.value)
        else:
            self._all_check_state = int(Qt.CheckState.PartiallyChecked.value)

    # --- Slots / Actions ---

    @Slot()
    def openAddFilesDialog(self) -> None:
        from PySide6.QtWidgets import QFileDialog

        files, _ = QFileDialog.getOpenFileNames(
            None,
            "Select Files to Rename",
            str(Path.home()),
        )
        if files:
            self.addPaths(files)

    @Slot()
    def openAddFolderDialog(self) -> None:
        from PySide6.QtWidgets import QFileDialog

        folder = QFileDialog.getExistingDirectory(
            None,
            "Select Folder to Add",
            str(Path.home()),
            QFileDialog.Option.ShowDirsOnly,
        )
        if folder:
            self.addPaths([folder])

    @Slot("QVariantList")
    def addUrls(self, urls: list[Any]) -> None:
        paths: list[str] = []
        for u in urls:
            if isinstance(u, QUrl):
                local = u.toLocalFile()
                if local:
                    paths.append(local)
            elif isinstance(u, str):
                qurl = QUrl(u)
                local = qurl.toLocalFile() if qurl.isLocalFile() else u
                if local:
                    paths.append(local)
        if paths:
            self.addPaths(paths)

    @Slot("QVariantList")
    def addPaths(self, raw_paths: list[str]) -> None:
        collected = collect_paths(
            raw_paths,
            recursive=self._recursive,
            include_hidden=self._include_hidden,
        )
        added = self._model.add_items(collected)
        if added > 0:
            self._recalculate()
            self.notificationRequested.emit(
                f"Added {added} item{'s' if added != 1 else ''}", "positive"
            )

    @Slot(int)
    def toggleExpanded(self, row: int) -> None:
        self._model.toggle_expanded(row)

    @Slot(int)
    def removeItem(self, row: int) -> None:
        self._model.remove_at(row)
        self._recalculate()

    @Slot()
    def clearItems(self) -> None:
        self._model.clear()
        self._update_stats()
        self.statsChanged.emit()

    @Slot(int, bool)
    def setItemEnabled(self, row: int, enabled: bool) -> None:
        self._model.set_item_enabled(row, enabled)
        self._recalculate()

    @Slot(bool)
    def setAllEnabled(self, enabled: bool) -> None:
        for item in self._model.items:
            item.enabled = enabled
        self._recalculate()

    @Slot()
    def applyRename(self) -> None:
        if not self.canRename:
            return
        result = execute_batch(self._model.items)
        if result.record and result.record.operations:
            self._undo_stack.append(result.record)
            self.historyChanged.emit()

        self._model.rebuild_after_path_changes()
        self._recalculate()

        if result.ok:
            count = result.success_count
            self.notificationRequested.emit(
                f"Successfully renamed {count} item{'s' if count != 1 else ''}.",
                "positive",
            )
        else:
            err_msg = result.errors[0][1] if result.errors else "Unknown error"
            self.notificationRequested.emit(
                f"Renamed {result.success_count} item(s) with {len(result.errors)} error(s): {err_msg}",
                "error",
            )

    @Slot()
    def undoLastBatch(self) -> None:
        if not self._undo_stack:
            return
        record = self._undo_stack.pop()
        self.historyChanged.emit()
        result = undo_batch(record, self._model.items)
        self._model.rebuild_after_path_changes()
        self._recalculate()
        if result.ok:
            count = result.success_count
            self.notificationRequested.emit(
                f"Reverted {count} renamed item{'s' if count != 1 else ''}.",
                "positive",
            )
        else:
            err_msg = result.errors[0][1] if result.errors else "Unknown error"
            self.notificationRequested.emit(
                f"Undo encountered errors: {err_msg}",
                "error",
            )

    def _recalculate(self) -> None:
        evaluate_preview(
            self._model.items,
            self._rule,
            strict_cross_platform=self._strict_cross_platform,
        )
        self._model.refresh_after_evaluate()
        self._update_stats()
        self.statsChanged.emit()
