# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests for namr.core and namr.controller."""

from __future__ import annotations

from pathlib import Path
import unittest

from namr.core import (
    FindReplaceRule,
    ItemStatus,
    RenameItem,
    TargetScope,
    collect_paths,
    evaluate_preview,
    execute_batch,
    undo_batch,
    validate_filename,
)
from tempfile import TemporaryDirectory


class TestFindReplaceRule(unittest.TestCase):
    def test_basic_find_replace_preserves_extension(self) -> None:
        rule = FindReplaceRule(
            find_text="draft",
            replace_text="final",
            case_sensitive=True,
            include_extension=False,
        )
        self.assertEqual(rule.compute_new_name("report_draft.draft", is_dir=False), "report_final.draft")

    def test_include_extension(self) -> None:
        rule = FindReplaceRule(
            find_text="jpeg",
            replace_text="jpg",
            include_extension=True,
        )
        self.assertEqual(rule.compute_new_name("photo.jpeg", is_dir=False), "photo.jpg")

    def test_case_insensitive_replace(self) -> None:
        rule = FindReplaceRule(
            find_text="IMG",
            replace_text="photo",
            case_sensitive=False,
        )
        self.assertEqual(rule.compute_new_name("img_001_IMG.png", is_dir=False), "photo_001_photo.png")

    def test_target_scope_filtering(self) -> None:
        files_only = FindReplaceRule(
            find_text="old_", replace_text="new_", target_scope=TargetScope.FILES_ONLY
        )
        self.assertEqual(files_only.compute_new_name("old_file.txt", is_dir=False), "new_file.txt")
        self.assertEqual(files_only.compute_new_name("old_folder", is_dir=True), "old_folder")

        dirs_only = FindReplaceRule(
            find_text="old_", replace_text="new_", target_scope=TargetScope.DIRS_ONLY
        )
        self.assertEqual(dirs_only.compute_new_name("old_file.txt", is_dir=False), "old_file.txt")
        self.assertEqual(dirs_only.compute_new_name("old_folder", is_dir=True), "new_folder")

    def test_source_and_target_diff_html_and_hidden_dotfiles(self) -> None:
        # Hidden dotfile like ".bashrc" should be treated as stem, not extension
        rule = FindReplaceRule(find_text="bash", replace_text="zsh", include_extension=False)
        self.assertEqual(rule.compute_new_name(".bashrc", is_dir=False), ".zshrc")
        self.assertIn("#f39c12", rule.compute_source_diff_html(".bashrc", is_dir=False))
        self.assertIn("#2ecc71", rule.compute_diff_html(".bashrc", is_dir=False))

        # Deletion diff uses strikethrough red in both source and target preview
        del_rule = FindReplaceRule(find_text="_temp", replace_text="")
        self.assertIn("<s><font color='#e74c3c'>_temp</font></s>", del_rule.compute_source_diff_html("doc_temp.txt", is_dir=False))
        self.assertIn("<s><font color='#e74c3c'>_temp</font></s>", del_rule.compute_diff_html("doc_temp.txt", is_dir=False))


class TestValidationAndConflicts(unittest.TestCase):
    def test_validate_filename(self) -> None:
        self.assertIsNotNone(validate_filename(""))
        self.assertIsNotNone(validate_filename(".."))
        self.assertIsNotNone(validate_filename("foo/bar"))
        self.assertIsNone(validate_filename("valid_name:1.txt", strict_cross_platform=False))
        self.assertIsNotNone(validate_filename("invalid_win:1.txt", strict_cross_platform=True))
        self.assertIsNotNone(validate_filename("CON.txt", strict_cross_platform=True))

    def test_duplicate_conflict_detection(self) -> None:
        with TemporaryDirectory() as tmp:
            p1 = Path(tmp) / "item_1.txt"
            p2 = Path(tmp) / "item_2.txt"
            p1.touch()
            p2.touch()

            items = [
                RenameItem(source_path=p1, is_dir=False),
                RenameItem(source_path=p2, is_dir=False),
            ]
            # Rule that collapses both names if we replace '1' with '2'
            rule = FindReplaceRule(find_text="1", replace_text="2")
            evaluate_preview(items, rule)

            self.assertEqual(items[0].status, ItemStatus.CONFLICT)
            self.assertEqual(items[1].status, ItemStatus.CONFLICT)

    def test_existing_file_on_disk_conflict_and_invalid_diff_color(self) -> None:
        with TemporaryDirectory() as tmp:
            base = Path(tmp)
            src = base / "episode_01.mkv"
            existing = base / "episode_02.mkv"
            src.touch()
            existing.touch()

            # Renaming onto an unselected file that already exists on disk -> CONFLICT
            items = [RenameItem(source_path=src, is_dir=False)]
            evaluate_preview(items, FindReplaceRule(find_text="01", replace_text="02"))
            self.assertEqual(items[0].status, ItemStatus.CONFLICT)
            self.assertEqual(items[0].error_message, "File already exists on disk")

            # Invalid character replacement turns diff_html red instead of green
            evaluate_preview(items, FindReplaceRule(find_text="01", replace_text=">"))
            self.assertEqual(items[0].status, ItemStatus.INVALID)
            self.assertIn("#e74c3c", items[0].diff_html)
            self.assertNotIn("#2ecc71", items[0].diff_html)


class TestBatchExecutionAndUndo(unittest.TestCase):
    def test_execute_and_undo_with_nested_directories(self) -> None:
        with TemporaryDirectory() as tmp:
            base = Path(tmp)
            parent_dir = base / "old_project"
            parent_dir.mkdir()
            child_file = parent_dir / "old_notes.txt"
            child_file.write_text("hello")

            collected = collect_paths([parent_dir], recursive=True)
            items = [RenameItem(source_path=p, is_dir=is_d) for p, is_d in collected]

            rule = FindReplaceRule(find_text="old", replace_text="new")
            evaluate_preview(items, rule)

            result = execute_batch(items)
            self.assertTrue(result.ok)
            self.assertEqual(result.success_count, 2)
            self.assertTrue((base / "new_project" / "new_notes.txt").exists())

            # Now undo
            assert result.record is not None
            undo_res = undo_batch(result.record, items)
            self.assertTrue(undo_res.ok)
            self.assertEqual(undo_res.success_count, 2)
            self.assertTrue((base / "old_project" / "old_notes.txt").exists())

    def test_swap_cycle_in_same_directory(self) -> None:
        """Renaming a_1 -> a_2 while a_2 is also in the batch being renamed to a_22."""
        with TemporaryDirectory() as tmp:
            base = Path(tmp)
            f1 = base / "file_a.txt"
            f2 = base / "file_aa.txt"
            f1.write_text("one")
            f2.write_text("two")

            items = [
                RenameItem(source_path=f1, is_dir=False),
                RenameItem(source_path=f2, is_dir=False),
            ]
            rule = FindReplaceRule(find_text="a", replace_text="aa")
            evaluate_preview(items, rule)

            res = execute_batch(items)
            self.assertTrue(res.ok)
            self.assertEqual((base / "file_aa.txt").read_text(), "one")
            self.assertEqual((base / "file_aaaa.txt").read_text(), "two")


class TestTreeModel(unittest.TestCase):
    def test_tree_collapse_expand_and_hierarchy(self) -> None:
        from namr.controller import RenameItemModel

        with TemporaryDirectory() as tmp:
            base = Path(tmp)
            root_dir = base / "root_folder"
            sub_dir = root_dir / "sub_folder"
            sub_dir.mkdir(parents=True)
            f1 = root_dir / "a.txt"
            f2 = sub_dir / "b.txt"
            f1.touch()
            f2.touch()

            collected = collect_paths([root_dir], recursive=True)
            model = RenameItemModel()
            model.add_items(collected)

            # All 4 items visible initially: root_folder (0), sub_folder (1), b.txt (2), a.txt (1)
            self.assertEqual(model.rowCount(), 4)
            self.assertEqual(
                model.data(model.index(0, 0), RenameItemModel.OriginalNameRole),
                "root_folder",
            )
            self.assertEqual(
                model.data(model.index(0, 0), RenameItemModel.IndentLevelRole), 0
            )
            self.assertTrue(
                model.data(model.index(0, 0), RenameItemModel.HasChildrenRole)
            )
            self.assertEqual(
                model.data(model.index(1, 0), RenameItemModel.OriginalNameRole),
                "sub_folder",
            )
            self.assertEqual(
                model.data(model.index(1, 0), RenameItemModel.IndentLevelRole), 1
            )
            self.assertEqual(
                model.data(model.index(2, 0), RenameItemModel.OriginalNameRole),
                "b.txt",
            )
            self.assertEqual(
                model.data(model.index(2, 0), RenameItemModel.IndentLevelRole), 2
            )

            # Collapse sub_folder (row 1) -> hides b.txt
            model.toggle_expanded(1)
            self.assertEqual(model.rowCount(), 3)

            # Collapse root_folder (row 0) -> only root_folder visible
            model.toggle_expanded(0)
            self.assertEqual(model.rowCount(), 1)

            # Expand root_folder (row 0) and sub_folder (row 1) -> all 4 visible again
            model.toggle_expanded(0)
            model.toggle_expanded(1)
            self.assertEqual(model.rowCount(), 4)

    def test_controller_filtering_and_cascade_operations(self) -> None:
        from PySide6.QtCore import Qt
        from namr.controller import RenamerController

        with TemporaryDirectory() as tmp:
            base = Path(tmp)
            root_dir = base / "show_season"
            sub_dir = root_dir / "extras"
            sub_dir.mkdir(parents=True)
            f_match = sub_dir / "clip_match.mkv"
            f_other = root_dir / "poster.jpg"
            f_match.touch()
            f_other.touch()

            ctrl = RenamerController()
            ctrl.addPaths([str(root_dir)])
            self.assertEqual(ctrl.totalCount, 4)
            self.assertEqual(ctrl.allCheckState, int(Qt.CheckState.Checked.value))

            # Filter by findText="match" and enable showChangedOnly
            ctrl.findText = "match"
            ctrl.replaceText = "renamed"
            self.assertEqual(ctrl.readyCount, 1)

            ctrl.showChangedOnly = True
            # Only clip_match.mkv and its ancestor folders (show_season, extras) should be visible (poster.jpg hidden)
            self.assertEqual(ctrl.itemModel.rowCount(), 3)
            ctrl.showChangedOnly = False
            self.assertEqual(ctrl.itemModel.rowCount(), 4)

            # Unchecking sub_dir (row 1: extras) cascades to clip_match.mkv -> partially checked state
            ctrl.setItemEnabled(1, False)
            self.assertEqual(ctrl.allCheckState, int(Qt.CheckState.PartiallyChecked.value))
            self.assertEqual(ctrl.readyCount, 0)

            # Removing sub_dir (row 1) removes both extras and its child clip_match.mkv
            ctrl.removeItem(1)
            self.assertEqual(ctrl.totalCount, 2)

    def test_collapsed_folders_preserved_across_rename_and_undo(self) -> None:
        from namr.controller import RenameItemModel, RenamerController

        with TemporaryDirectory() as tmp:
            base = Path(tmp)
            root_dir = base / "root_draft"
            sub_dir = root_dir / "sub_draft"
            sub_dir.mkdir(parents=True)
            f1 = sub_dir / "file_draft.txt"
            f1.touch()

            ctrl = RenamerController()
            ctrl.addPaths([str(root_dir)])
            self.assertEqual(ctrl.itemModel.rowCount(), 3)

            # Collapse sub_draft (row 1) -> hides file_draft.txt
            ctrl.toggleExpanded(1)
            self.assertEqual(ctrl.itemModel.rowCount(), 2)
            self.assertFalse(
                ctrl.itemModel.data(
                    ctrl.itemModel.index(1, 0), RenameItemModel.IsExpandedRole
                )
            )

            # Rename "draft" -> "final" across all items (including the collapsed folder)
            ctrl.findText = "draft"
            ctrl.replaceText = "final"
            ctrl.applyRename()

            # sub_final (row 1) must still be collapsed after rename!
            self.assertEqual(ctrl.itemModel.rowCount(), 2)
            self.assertEqual(
                ctrl.itemModel.data(
                    ctrl.itemModel.index(1, 0), RenameItemModel.OriginalNameRole
                ),
                "sub_final",
            )
            self.assertFalse(
                ctrl.itemModel.data(
                    ctrl.itemModel.index(1, 0), RenameItemModel.IsExpandedRole
                )
            )

            # Undo rename -> sub_draft (row 1) must still be collapsed!
            ctrl.undoLastBatch()
            self.assertEqual(ctrl.itemModel.rowCount(), 2)
            self.assertEqual(
                ctrl.itemModel.data(
                    ctrl.itemModel.index(1, 0), RenameItemModel.OriginalNameRole
                ),
                "sub_draft",
            )
            self.assertFalse(
                ctrl.itemModel.data(
                    ctrl.itemModel.index(1, 0), RenameItemModel.IsExpandedRole
                )
            )


if __name__ == "__main__":
    unittest.main()
