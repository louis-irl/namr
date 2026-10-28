// SPDX-License-Identifier: Unlicense
import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

Kirigami.ApplicationWindow {
    id: root
    title: qsTr("Namr")
    width: 1120
    height: 720
    minimumWidth: 780
    minimumHeight: 500

    // Notification handling from Python controller
    Connections {
        target: renamerController
        function onNotificationRequested(message, msgType) {
            let kType = Kirigami.MessageType.Information
            if (msgType === "positive") {
                kType = Kirigami.MessageType.Positive
            } else if (msgType === "warning") {
                kType = Kirigami.MessageType.Warning
            } else if (msgType === "error") {
                kType = Kirigami.MessageType.Error
            }
            banner.type = kType
            banner.text = message
            banner.visible = true
            bannerTimer.restart()
        }
    }

    Timer {
        id: bannerTimer
        interval: 4000
        repeat: false
        onTriggered: banner.visible = false
    }

    pageStack.globalToolBar.style: Kirigami.ApplicationHeaderStyle.None

    // Application-wide keyboard shortcuts
    Shortcut {
        sequence: "Ctrl+O"
        onActivated: renamerController.openAddFilesDialog()
    }
    Shortcut {
        sequence: "Ctrl+Shift+O"
        onActivated: renamerController.openAddFolderDialog()
    }
    Shortcut {
        sequences: [StandardKey.Undo]
        enabled: renamerController.canUndo
        onActivated: renamerController.undoLastBatch()
    }
    Shortcut {
        sequence: "Ctrl+?"
        onActivated: shortcutsDialog.open()
    }

    pageStack.initialPage: Kirigami.Page {
        id: mainPage
        padding: 0

        header: QQC2.ToolBar {
            leftPadding: Kirigami.Units.smallSpacing
            rightPadding: Kirigami.Units.smallSpacing

            contentItem: RowLayout {
                spacing: Kirigami.Units.smallSpacing

                QQC2.ToolButton {
                    text: qsTr("Add Files…")
                    icon.name: "document-open"
                    display: QQC2.AbstractButton.TextBesideIcon
                    focusPolicy: Qt.NoFocus
                    QQC2.ToolTip.visible: hovered
                    QQC2.ToolTip.text: qsTr("Add files to rename (Ctrl+O)")
                    onClicked: renamerController.openAddFilesDialog()
                }

                QQC2.ToolButton {
                    text: qsTr("Add Folder…")
                    icon.name: "folder-open"
                    display: QQC2.AbstractButton.TextBesideIcon
                    focusPolicy: Qt.NoFocus
                    QQC2.ToolTip.visible: hovered
                    QQC2.ToolTip.text: qsTr("Add a folder to rename (Ctrl+Shift+O)")
                    onClicked: renamerController.openAddFolderDialog()
                }

                QQC2.ToolSeparator {}

                QQC2.ToolButton {
                    text: qsTr("Undo")
                    icon.name: "edit-undo"
                    display: QQC2.AbstractButton.TextBesideIcon
                    focusPolicy: Qt.NoFocus
                    enabled: renamerController.canUndo
                    QQC2.ToolTip.visible: hovered
                    QQC2.ToolTip.text: qsTr("Undo last batch rename (Ctrl+Z)")
                    onClicked: renamerController.undoLastBatch()
                }

                QQC2.ToolButton {
                    text: qsTr("Clear")
                    icon.name: "edit-clear-list"
                    display: QQC2.AbstractButton.TextBesideIcon
                    focusPolicy: Qt.NoFocus
                    enabled: renamerController.totalCount > 0
                    QQC2.ToolTip.visible: hovered
                    QQC2.ToolTip.text: qsTr("Remove all items from the list")
                    onClicked: renamerController.clearItems()
                }

                Item {
                    Layout.fillWidth: true
                }

                QQC2.ToolButton {
                    id: menuButton
                    icon.name: "application-menu"
                    display: QQC2.AbstractButton.IconOnly
                    focusPolicy: Qt.NoFocus
                    down: hamburgerMenu.visible
                    QQC2.ToolTip.visible: hovered && !hamburgerMenu.visible
                    QQC2.ToolTip.text: qsTr("Menu")
                    onClicked: {
                        if (hamburgerMenu.visible) {
                            hamburgerMenu.close()
                        } else {
                            hamburgerMenu.popup(menuButton, 0, menuButton.height)
                        }
                    }

                    QQC2.Menu {
                        id: hamburgerMenu

                        QQC2.MenuItem {
                            text: qsTr("Keyboard Shortcuts…")
                            icon.name: "configure-shortcuts"
                            onTriggered: shortcutsDialog.open()
                        }

                        QQC2.MenuSeparator {}

                        QQC2.MenuItem {
                            text: qsTr("About Namr…")
                            icon.name: "help-about"
                            onTriggered: aboutDialog.open()
                        }
                    }
                }
            }
        }

        // Whole-window Drag & Drop area
        DropArea {
            id: globalDropArea
            anchors.fill: parent
            onDropped: function(drop) {
                if (drop.hasUrls) {
                    renamerController.addUrls(drop.urls)
                    drop.acceptProposedAction()
                }
            }

            Rectangle {
                anchors.fill: parent
                z: 99
                visible: globalDropArea.containsDrag
                color: Qt.rgba(Kirigami.Theme.highlightColor.r,
                               Kirigami.Theme.highlightColor.g,
                               Kirigami.Theme.highlightColor.b, 0.16)
                border.color: Kirigami.Theme.highlightColor
                border.width: 2
                radius: Kirigami.Units.smallSpacing
            }
        }

        // Passive pointer observer: clears highlighted filename text when clicking outside the active TextEdit
        Item {
            anchors.fill: parent
            z: 9999
            PointHandler {
                acceptedButtons: Qt.LeftButton
                onActiveChanged: {
                    if (active && previewList.activeEditor && !textContextMenu.visible) {
                        let ed = previewList.activeEditor
                        let p = ed.mapFromItem(mainPage, point.position.x, point.position.y)
                        if (p.x < 0 || p.y < 0 || p.x > ed.width || p.y > ed.height) {
                            ed.deselect()
                            ed.focus = false
                            previewList.activeEditor = null
                        }
                    }
                }
            }
        }

        // Floating toast overlay for transient status notifications (never shifts layout)
        ColumnLayout {
            z: 100
            anchors.bottom: parent.bottom
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.bottomMargin: Kirigami.Units.largeSpacing * 1.5
            width: Math.min(420, mainPage.width - (Kirigami.Units.largeSpacing * 4))
            spacing: Kirigami.Units.smallSpacing

            Kirigami.InlineMessage {
                id: banner
                Layout.fillWidth: true
                showCloseButton: true
                visible: false
            }
        }

        // Main Split Area: Left Rule Configuration + Right Live Preview
        QQC2.SplitView {
            anchors.fill: parent
            orientation: Qt.Horizontal

            // --- Left Sidebar: Rename Rule Configuration ---
            QQC2.Pane {
                QQC2.SplitView.preferredWidth: 310
                QQC2.SplitView.minimumWidth: 260
                QQC2.SplitView.maximumWidth: 440
                padding: 0

                background: Rectangle {
                    color: Kirigami.Theme.backgroundColor
                }

                ColumnLayout {
                    anchors.fill: parent
                    spacing: 0

                    // Rule Form Area
                    ColumnLayout {
                        Layout.fillWidth: true
                        Layout.margins: Kirigami.Units.largeSpacing
                        spacing: Kirigami.Units.smallSpacing

                        Kirigami.Heading {
                            level: 3
                            text: qsTr("Find & Replace")
                            Layout.bottomMargin: Kirigami.Units.smallSpacing
                        }

                        QQC2.Label {
                            text: qsTr("Find:")
                        }

                        QQC2.TextField {
                            id: findField
                            Layout.fillWidth: true
                            placeholderText: qsTr("Text to find…")
                            text: renamerController.findText
                            onTextEdited: renamerController.findText = text
                            KeyNavigation.tab: replaceField
                            KeyNavigation.backtab: renameBtn

                            rightPadding: clearFindBtn.visible ? clearFindBtn.width + Kirigami.Units.smallSpacing : undefined
                            QQC2.ToolButton {
                                id: clearFindBtn
                                anchors.right: parent.right
                                anchors.verticalCenter: parent.verticalCenter
                                anchors.rightMargin: 2
                                width: Kirigami.Units.iconSizes.smallMedium
                                height: Kirigami.Units.iconSizes.smallMedium
                                flat: true
                                padding: 0
                                focusPolicy: Qt.NoFocus
                                activeFocusOnTab: false
                                visible: findField.text.length > 0
                                icon.name: "edit-clear-locationbar-rtl"
                                icon.width: Kirigami.Units.iconSizes.small
                                icon.height: Kirigami.Units.iconSizes.small
                                onClicked: {
                                    findField.clear()
                                    renamerController.findText = ""
                                }
                            }
                        }

                        QQC2.Label {
                            text: qsTr("Replace with:")
                            Layout.topMargin: Kirigami.Units.smallSpacing
                        }

                        QQC2.TextField {
                            id: replaceField
                            Layout.fillWidth: true
                            placeholderText: qsTr("Replacement (empty to delete)…")
                            text: renamerController.replaceText
                            onTextEdited: renamerController.replaceText = text
                            KeyNavigation.tab: scopeCombo
                            KeyNavigation.backtab: findField

                            rightPadding: clearReplaceBtn.visible ? clearReplaceBtn.width + Kirigami.Units.smallSpacing : undefined
                            QQC2.ToolButton {
                                id: clearReplaceBtn
                                anchors.right: parent.right
                                anchors.verticalCenter: parent.verticalCenter
                                anchors.rightMargin: 2
                                width: Kirigami.Units.iconSizes.smallMedium
                                height: Kirigami.Units.iconSizes.smallMedium
                                flat: true
                                padding: 0
                                focusPolicy: Qt.NoFocus
                                activeFocusOnTab: false
                                visible: replaceField.text.length > 0
                                icon.name: "edit-clear-locationbar-rtl"
                                icon.width: Kirigami.Units.iconSizes.small
                                icon.height: Kirigami.Units.iconSizes.small
                                onClicked: {
                                    replaceField.clear()
                                    renamerController.replaceText = ""
                                }
                            }
                        }

                        QQC2.Label {
                            text: qsTr("Apply to:")
                            Layout.topMargin: Kirigami.Units.smallSpacing
                        }

                        QQC2.ComboBox {
                            id: scopeCombo
                            Layout.fillWidth: true
                            focusPolicy: Qt.StrongFocus
                            activeFocusOnTab: true
                            KeyNavigation.tab: caseSensitiveCheck
                            KeyNavigation.backtab: replaceField
                            model: [
                                { text: qsTr("Files and Folders"), value: "both" },
                                { text: qsTr("Files Only"), value: "files_only" },
                                { text: qsTr("Folders Only"), value: "dirs_only" }
                            ]
                            textRole: "text"
                            valueRole: "value"
                            currentIndex: 0
                            onCurrentValueChanged: {
                                if (currentValue !== undefined) {
                                    renamerController.targetScope = currentValue
                                }
                            }
                            Connections {
                                target: scopeCombo.popup
                                function onOpened() {
                                    // org.kde.desktop ComboBox uses a Menu popup that doesn't grab
                                    // keyboard focus on open unless forced onto its contentItem
                                    scopeCombo.popup.currentIndex = scopeCombo.currentIndex
                                    if (scopeCombo.popup.contentItem) {
                                        scopeCombo.popup.contentItem.forceActiveFocus()
                                    }
                                }
                            }
                            Keys.onUpPressed: function(event) {
                                decrease()
                                event.accepted = true
                            }
                            Keys.onDownPressed: function(event) {
                                increase()
                                event.accepted = true
                            }
                        }

                        QQC2.CheckBox {
                            id: caseSensitiveCheck
                            Layout.topMargin: Kirigami.Units.smallSpacing
                            text: qsTr("Case sensitive")
                            focusPolicy: Qt.StrongFocus
                            activeFocusOnTab: true
                            KeyNavigation.tab: includeExtCheck
                            KeyNavigation.backtab: scopeCombo
                            checked: renamerController.caseSensitive
                            onToggled: renamerController.caseSensitive = checked
                        }

                        QQC2.CheckBox {
                            id: includeExtCheck
                            text: qsTr("Include file extension")
                            focusPolicy: Qt.StrongFocus
                            activeFocusOnTab: true
                            KeyNavigation.tab: recursiveCheck
                            KeyNavigation.backtab: caseSensitiveCheck
                            checked: renamerController.includeExtension
                            onToggled: renamerController.includeExtension = checked
                        }

                        Kirigami.Separator {
                            Layout.fillWidth: true
                            Layout.topMargin: Kirigami.Units.mediumSpacing
                            Layout.bottomMargin: Kirigami.Units.smallSpacing
                        }

                        Kirigami.Heading {
                            level: 3
                            text: qsTr("Behavior")
                            Layout.bottomMargin: 2
                        }

                        QQC2.CheckBox {
                            id: recursiveCheck
                            text: qsTr("Include subfolders recursively")
                            focusPolicy: Qt.StrongFocus
                            activeFocusOnTab: true
                            KeyNavigation.tab: strictNamesCheck
                            KeyNavigation.backtab: includeExtCheck
                            checked: renamerController.recursiveScan
                            onToggled: renamerController.recursiveScan = checked
                            QQC2.ToolTip.visible: hovered
                            QQC2.ToolTip.text: qsTr("When adding folders, also load all files and folders inside them")
                        }

                        QQC2.CheckBox {
                            id: strictNamesCheck
                            text: qsTr("Strict Windows/macOS names")
                            focusPolicy: Qt.StrongFocus
                            activeFocusOnTab: true
                            KeyNavigation.tab: changedOnlyCheck
                            KeyNavigation.backtab: recursiveCheck
                            checked: renamerController.strictCrossPlatform
                            onToggled: renamerController.strictCrossPlatform = checked
                            QQC2.ToolTip.visible: hovered
                            QQC2.ToolTip.text: qsTr("Warn on characters reserved on Windows (< > : \" \\ | ? *)")
                        }

                        QQC2.CheckBox {
                            id: changedOnlyCheck
                            text: qsTr("Show only affected items")
                            focusPolicy: Qt.StrongFocus
                            activeFocusOnTab: true
                            KeyNavigation.tab: renameBtn.enabled ? renameBtn : findField
                            KeyNavigation.backtab: strictNamesCheck
                            checked: renamerController.showChangedOnly
                            onToggled: renamerController.showChangedOnly = checked
                            QQC2.ToolTip.visible: hovered
                            QQC2.ToolTip.text: qsTr("Hide unchanged files and folders in the preview tree")
                        }
                    }

                    Item {
                        Layout.fillHeight: true
                    }

                    Kirigami.Separator {
                        Layout.fillWidth: true
                    }

                    // Bottom Action Footer (KDE HIG standard footer bar)
                    Rectangle {
                        Layout.fillWidth: true
                        implicitHeight: footerCol.implicitHeight + (Kirigami.Units.largeSpacing * 2)
                        color: Kirigami.Theme.alternateBackgroundColor

                        ColumnLayout {
                            id: footerCol
                            anchors.fill: parent
                            anchors.margins: Kirigami.Units.largeSpacing
                            spacing: Kirigami.Units.smallSpacing

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: Kirigami.Units.smallSpacing

                                QQC2.Label {
                                    text: qsTr("%1 items").arg(renamerController.totalCount)
                                    font.pointSize: Kirigami.Theme.smallFont.pointSize
                                    opacity: 0.75
                                }

                                Item { Layout.fillWidth: true }

                                QQC2.Label {
                                    visible: renamerController.readyCount > 0
                                    text: qsTr("%1 ready").arg(renamerController.readyCount)
                                    font.pointSize: Kirigami.Theme.smallFont.pointSize
                                    font.bold: true
                                    color: Kirigami.Theme.positiveTextColor
                                }

                                QQC2.Label {
                                    visible: renamerController.readyCount > 0 && renamerController.conflictCount > 0
                                    text: "·"
                                    font.pointSize: Kirigami.Theme.smallFont.pointSize
                                    opacity: 0.6
                                }

                                QQC2.Label {
                                    visible: renamerController.conflictCount > 0
                                    text: qsTr("%1 conflict(s)").arg(renamerController.conflictCount)
                                    font.pointSize: Kirigami.Theme.smallFont.pointSize
                                    font.bold: true
                                    color: Kirigami.Theme.negativeTextColor
                                }

                                QQC2.Label {
                                    visible: renamerController.readyCount === 0 && renamerController.conflictCount === 0
                                    text: qsTr("No changes")
                                    font.pointSize: Kirigami.Theme.smallFont.pointSize
                                    color: Kirigami.Theme.disabledTextColor
                                }
                            }

                            QQC2.Button {
                                id: renameBtn
                                Layout.fillWidth: true
                                focusPolicy: Qt.StrongFocus
                                activeFocusOnTab: true
                                KeyNavigation.tab: findField
                                KeyNavigation.backtab: changedOnlyCheck
                                text: renamerController.readyCount > 0
                                      ? qsTr("Rename %1 Item(s)").arg(renamerController.readyCount)
                                      : qsTr("Rename")
                                icon.name: "dialog-ok-apply"
                                highlighted: true
                                enabled: renamerController.canRename
                                onClicked: renamerController.applyRename()
                            }
                        }
                    }
                }
            }

            // --- Right Area: Live Preview Table ---
            Item {
                id: tableContainer
                QQC2.SplitView.fillWidth: true
                QQC2.SplitView.fillHeight: true

                // Shared column geometry with user-resizable ratios
                readonly property real rowWidth: previewList.width
                readonly property real hPad: Kirigami.Units.mediumSpacing
                readonly property real colSpacing: Kirigami.Units.largeSpacing
                readonly property real checkColWidth: 22
                readonly property real actionColWidth: 24
                property real statusColWidth: 190
                property real origSplitRatio: 0.50

                readonly property real minNameColWidth: 110
                readonly property real minStatusColWidth: 120
                readonly property real flexibleWidth: Math.max(
                    minNameColWidth * 2,
                    rowWidth - (hPad * 2) - checkColWidth - statusColWidth - actionColWidth - (colSpacing * 4)
                )
                readonly property real origColWidth: Math.max(
                    minNameColWidth,
                    Math.min(flexibleWidth - minNameColWidth, Math.floor(flexibleWidth * origSplitRatio))
                )
                readonly property real newColWidth: Math.max(
                    minNameColWidth,
                    Math.floor(flexibleWidth - origColWidth)
                )

                ColumnLayout {
                    anchors.fill: parent
                    spacing: 0

                    // Table Column Header Bar (with draggable column splitters)
                    Rectangle {
                        id: headerBar
                        Layout.fillWidth: true
                        height: Kirigami.Units.gridUnit * 1.7
                        color: Kirigami.Theme.backgroundColor
                        visible: renamerController.totalCount > 0

                        RowLayout {
                            id: headerRow
                            anchors.top: parent.top
                            anchors.bottom: parent.bottom
                            anchors.left: parent.left
                            width: tableContainer.rowWidth
                            anchors.leftMargin: tableContainer.hPad
                            anchors.rightMargin: tableContainer.hPad
                            spacing: tableContainer.colSpacing

                            QQC2.CheckBox {
                                Layout.preferredWidth: tableContainer.checkColWidth
                                Layout.maximumWidth: tableContainer.checkColWidth
                                tristate: true
                                checkState: renamerController.allCheckState
                                nextCheckState: function() {
                                    return checkState === Qt.Checked ? Qt.Unchecked : Qt.Checked
                                }
                                QQC2.ToolTip.visible: hovered
                                QQC2.ToolTip.text: qsTr("Select or deselect all items")
                                onClicked: renamerController.setAllEnabled(checkState === Qt.Checked)
                            }

                            QQC2.Label {
                                id: origHeaderLabel
                                Layout.preferredWidth: tableContainer.origColWidth
                                Layout.maximumWidth: tableContainer.origColWidth
                                text: qsTr("Original Name")
                                font.bold: true
                                font.pointSize: Kirigami.Theme.smallFont.pointSize
                                opacity: 0.85
                                elide: Text.ElideRight
                            }

                            QQC2.Label {
                                id: newHeaderLabel
                                Layout.preferredWidth: tableContainer.newColWidth
                                Layout.maximumWidth: tableContainer.newColWidth
                                text: qsTr("New Name (Preview)")
                                font.bold: true
                                font.pointSize: Kirigami.Theme.smallFont.pointSize
                                opacity: 0.85
                                elide: Text.ElideRight
                            }

                            QQC2.Label {
                                id: statusHeaderLabel
                                Layout.preferredWidth: tableContainer.statusColWidth
                                Layout.maximumWidth: tableContainer.statusColWidth
                                text: qsTr("Status")
                                font.bold: true
                                font.pointSize: Kirigami.Theme.smallFont.pointSize
                                opacity: 0.85
                                elide: Text.ElideRight
                            }

                            Item {
                                Layout.preferredWidth: tableContainer.actionColWidth
                                Layout.maximumWidth: tableContainer.actionColWidth
                            }
                        }

                        // Resizer 1: between Original Name and New Name
                        MouseArea {
                            id: splitHandle1
                            x: headerRow.x + origHeaderLabel.x + origHeaderLabel.width + (tableContainer.colSpacing / 2) - (width / 2)
                            y: 0
                            width: 9
                            height: parent.height
                            cursorShape: Qt.SplitHCursor
                            hoverEnabled: true
                            property real startX: 0
                            property real startOrigWidth: 0
                            onPressed: function(mouse) {
                                startX = mapToItem(headerBar, mouse.x, 0).x
                                startOrigWidth = tableContainer.origColWidth
                            }
                            onPositionChanged: function(mouse) {
                                if (pressed && tableContainer.flexibleWidth > 0) {
                                    let curX = mapToItem(headerBar, mouse.x, 0).x
                                    let newW = Math.max(
                                        tableContainer.minNameColWidth,
                                        Math.min(tableContainer.flexibleWidth - tableContainer.minNameColWidth, startOrigWidth + (curX - startX))
                                    )
                                    tableContainer.origSplitRatio = newW / tableContainer.flexibleWidth
                                }
                            }
                            Rectangle {
                                anchors.centerIn: parent
                                width: 1
                                height: parent.height - 8
                                color: splitHandle1.containsMouse || splitHandle1.pressed
                                       ? Kirigami.Theme.highlightColor
                                       : Kirigami.Theme.textColor
                                opacity: splitHandle1.containsMouse || splitHandle1.pressed ? 0.9 : 0.2
                            }
                        }

                        // Resizer 2: between New Name and Status
                        MouseArea {
                            id: splitHandle2
                            x: headerRow.x + newHeaderLabel.x + newHeaderLabel.width + (tableContainer.colSpacing / 2) - (width / 2)
                            y: 0
                            width: 9
                            height: parent.height
                            cursorShape: Qt.SplitHCursor
                            hoverEnabled: true
                            property real startX: 0
                            property real startStatusWidth: 0
                            onPressed: function(mouse) {
                                startX = mapToItem(headerBar, mouse.x, 0).x
                                startStatusWidth = tableContainer.statusColWidth
                            }
                            onPositionChanged: function(mouse) {
                                if (pressed) {
                                    let curX = mapToItem(headerBar, mouse.x, 0).x
                                    let maxStatus = Math.max(
                                        tableContainer.minStatusColWidth,
                                        tableContainer.rowWidth - (tableContainer.minNameColWidth * 2) - 120
                                    )
                                    tableContainer.statusColWidth = Math.max(
                                        tableContainer.minStatusColWidth,
                                        Math.min(maxStatus, startStatusWidth - (curX - startX))
                                    )
                                }
                            }
                            Rectangle {
                                anchors.centerIn: parent
                                width: 1
                                height: parent.height - 8
                                color: splitHandle2.containsMouse || splitHandle2.pressed
                                       ? Kirigami.Theme.highlightColor
                                       : Kirigami.Theme.textColor
                                opacity: splitHandle2.containsMouse || splitHandle2.pressed ? 0.9 : 0.2
                            }
                        }
                    }

                    Kirigami.Separator {
                        Layout.fillWidth: true
                        visible: renamerController.totalCount > 0
                    }

                    // Collapsible Tree Preview View
                    QQC2.ScrollView {
                        Layout.fillWidth: true
                        Layout.fillHeight: true

                        ListView {
                            id: previewList
                            clip: true
                            boundsBehavior: Flickable.StopAtBounds
                            model: renamerController.itemModel
                            property TextEdit activeEditor: null

                            // Shared context menu for selectable filename fields
                            QQC2.Menu {
                                id: textContextMenu
                                property TextEdit targetEditor: null

                                QQC2.MenuItem {
                                    text: qsTr("Copy")
                                    icon.name: "edit-copy"
                                    enabled: textContextMenu.targetEditor !== null
                                             && textContextMenu.targetEditor.selectedText.length > 0
                                    onTriggered: {
                                        if (textContextMenu.targetEditor) {
                                            textContextMenu.targetEditor.copy()
                                        }
                                    }
                                }

                                QQC2.MenuItem {
                                    text: qsTr("Select All")
                                    icon.name: "edit-select-all"
                                    enabled: textContextMenu.targetEditor !== null
                                    onTriggered: {
                                        if (textContextMenu.targetEditor) {
                                            textContextMenu.targetEditor.forceActiveFocus()
                                            textContextMenu.targetEditor.selectAll()
                                        }
                                    }
                                }
                            }

                            Kirigami.PlaceholderMessage {
                                anchors.centerIn: parent
                                width: parent.width - (Kirigami.Units.gridUnit * 4)
                                visible: previewList.count === 0
                                icon.name: renamerController.totalCount === 0 ? "edit-rename" : "view-filter"
                                text: renamerController.totalCount === 0
                                      ? qsTr("Drop files or folders here to begin")
                                      : qsTr("No affected items")
                                explanation: renamerController.totalCount === 0
                                             ? qsTr("Drag items from your file manager or use Add Files / Add Folder above.")
                                             : qsTr("None of the %1 loaded item(s) match the current Find & Replace rule.").arg(renamerController.totalCount)

                                helpfulAction: Kirigami.Action {
                                    enabled: renamerController.totalCount === 0
                                    icon.name: "document-open"
                                    text: qsTr("Add Files…")
                                    onTriggered: renamerController.openAddFilesDialog()
                                }
                            }

                            delegate: QQC2.Control {
                                id: rowDelegate
                                required property int index
                                required property string originalName
                                required property string newName
                                required property string sourceDiffHtml
                                required property string diffHtml
                                required property string parentDir
                                required property string sourcePath
                                required property bool isDir
                                required property bool itemEnabled
                                required property string status
                                required property string errorMessage
                                required property int indentLevel
                                required property bool hasChildren
                                required property bool isExpanded
                                required property bool showParentDir
                                required property string iconName

                                width: ListView.view.width
                                hoverEnabled: true
                                leftPadding: tableContainer.hPad
                                rightPadding: tableContainer.hPad
                                topPadding: 3
                                bottomPadding: 3

                                background: Rectangle {
                                    color: {
                                        if (rowDelegate.status === "conflict" || rowDelegate.status === "invalid") {
                                            return Qt.rgba(Kirigami.Theme.negativeBackgroundColor.r,
                                                           Kirigami.Theme.negativeBackgroundColor.g,
                                                           Kirigami.Theme.negativeBackgroundColor.b, 0.25)
                                        }
                                        if (rowDelegate.hovered) {
                                            return Qt.rgba(Kirigami.Theme.highlightColor.r,
                                                           Kirigami.Theme.highlightColor.g,
                                                           Kirigami.Theme.highlightColor.b, 0.12)
                                        }
                                        if (rowDelegate.status === "ready") {
                                            return Qt.rgba(Kirigami.Theme.positiveBackgroundColor.r,
                                                           Kirigami.Theme.positiveBackgroundColor.g,
                                                           Kirigami.Theme.positiveBackgroundColor.b, 0.12)
                                        }
                                        return (rowDelegate.index % 2 === 1)
                                               ? Kirigami.Theme.alternateBackgroundColor
                                               : "transparent"
                                    }
                                }

                                contentItem: RowLayout {
                                    spacing: tableContainer.colSpacing
                                    opacity: rowDelegate.itemEnabled ? 1.0 : 0.45

                                    QQC2.CheckBox {
                                        Layout.preferredWidth: tableContainer.checkColWidth
                                        Layout.maximumWidth: tableContainer.checkColWidth
                                        Layout.alignment: Qt.AlignVCenter
                                        topPadding: 0
                                        bottomPadding: 0
                                        checked: rowDelegate.itemEnabled
                                        onToggled: renamerController.setItemEnabled(rowDelegate.index, checked)
                                    }

                                    // Tree Indentation + Expand/Collapse Chevron + Folder/File Name
                                    RowLayout {
                                        Layout.preferredWidth: tableContainer.origColWidth
                                        Layout.maximumWidth: tableContainer.origColWidth
                                        Layout.alignment: Qt.AlignVCenter
                                        spacing: 4

                                        Item {
                                            Layout.preferredWidth: rowDelegate.indentLevel * (Kirigami.Units.gridUnit * 0.9)
                                            Layout.preferredHeight: 1
                                            visible: rowDelegate.indentLevel > 0
                                        }

                                        QQC2.ToolButton {
                                            Layout.preferredWidth: Kirigami.Units.iconSizes.small
                                            Layout.preferredHeight: Kirigami.Units.iconSizes.small
                                            Layout.alignment: Qt.AlignVCenter
                                            padding: 0
                                            flat: true
                                            visible: rowDelegate.hasChildren
                                            icon.name: rowDelegate.isExpanded ? "arrow-down" : "arrow-right"
                                            icon.width: Kirigami.Units.iconSizes.small
                                            icon.height: Kirigami.Units.iconSizes.small
                                            onClicked: renamerController.toggleExpanded(rowDelegate.index)
                                            QQC2.ToolTip.visible: hovered
                                            QQC2.ToolTip.text: rowDelegate.isExpanded ? qsTr("Collapse folder") : qsTr("Expand folder")
                                        }

                                        Item {
                                            Layout.preferredWidth: Kirigami.Units.iconSizes.small
                                            Layout.preferredHeight: Kirigami.Units.iconSizes.small
                                            visible: !rowDelegate.hasChildren
                                        }

                                        Kirigami.Icon {
                                            source: rowDelegate.iconName
                                            Layout.preferredWidth: Kirigami.Units.iconSizes.small
                                            Layout.preferredHeight: Kirigami.Units.iconSizes.small
                                            Layout.alignment: Qt.AlignVCenter

                                            MouseArea {
                                                anchors.fill: parent
                                                enabled: rowDelegate.hasChildren
                                                onDoubleClicked: renamerController.toggleExpanded(rowDelegate.index)
                                            }
                                        }

                                        TextEdit {
                                            id: origNameEdit
                                            Layout.fillWidth: true
                                            Layout.alignment: Qt.AlignVCenter
                                            topPadding: 0
                                            bottomPadding: 0
                                            readOnly: true
                                            selectByMouse: true
                                            activeFocusOnTab: false
                                            textFormat: TextEdit.RichText
                                            wrapMode: TextEdit.NoWrap
                                            clip: true
                                            text: rowDelegate.sourceDiffHtml
                                            font.family: Kirigami.Theme.defaultFont.family
                                            font.pointSize: Kirigami.Theme.defaultFont.pointSize
                                            font.bold: rowDelegate.isDir
                                            color: Kirigami.Theme.textColor
                                            selectionColor: Kirigami.Theme.highlightColor
                                            selectedTextColor: Kirigami.Theme.highlightedTextColor
                                            verticalAlignment: TextEdit.AlignVCenter
                                            onActiveFocusChanged: {
                                                if (activeFocus) {
                                                    if (previewList.activeEditor && previewList.activeEditor !== origNameEdit) {
                                                        previewList.activeEditor.deselect()
                                                    }
                                                    previewList.activeEditor = origNameEdit
                                                } else if (!textContextMenu.visible) {
                                                    deselect()
                                                }
                                            }
                                            onSelectedTextChanged: {
                                                if (selectedText.length > 0) {
                                                    previewList.activeEditor = origNameEdit
                                                }
                                            }
                                            QQC2.ToolTip.visible: rowDelegate.hovered && selectedText.length === 0
                                            QQC2.ToolTip.delay: 600
                                            QQC2.ToolTip.text: rowDelegate.sourcePath

                                            MouseArea {
                                                anchors.fill: parent
                                                acceptedButtons: Qt.RightButton
                                                cursorShape: Qt.IBeamCursor
                                                onClicked: {
                                                    origNameEdit.forceActiveFocus()
                                                    textContextMenu.targetEditor = origNameEdit
                                                    textContextMenu.popup()
                                                }
                                            }
                                        }

                                        QQC2.Label {
                                            visible: rowDelegate.showParentDir
                                            Layout.alignment: Qt.AlignVCenter
                                            text: rowDelegate.parentDir
                                            font.pointSize: Kirigami.Theme.smallFont.pointSize
                                            opacity: 0.5
                                            elide: Text.ElideMiddle
                                            Layout.maximumWidth: 110
                                        }
                                    }

                                    // New Name with Diff Highlight
                                    TextEdit {
                                        id: newNameEdit
                                        Layout.preferredWidth: tableContainer.newColWidth
                                        Layout.maximumWidth: tableContainer.newColWidth
                                        Layout.alignment: Qt.AlignVCenter
                                        topPadding: 0
                                        bottomPadding: 0
                                        readOnly: true
                                        selectByMouse: true
                                        activeFocusOnTab: false
                                        textFormat: TextEdit.RichText
                                        wrapMode: TextEdit.NoWrap
                                        clip: true
                                        text: rowDelegate.diffHtml
                                        font.family: Kirigami.Theme.defaultFont.family
                                        font.pointSize: Kirigami.Theme.defaultFont.pointSize
                                        color: Kirigami.Theme.textColor
                                        selectionColor: Kirigami.Theme.highlightColor
                                        selectedTextColor: Kirigami.Theme.highlightedTextColor
                                        verticalAlignment: TextEdit.AlignVCenter
                                        opacity: rowDelegate.status === "unchanged" ? 0.55 : 1.0
                                        onActiveFocusChanged: {
                                            if (activeFocus) {
                                                if (previewList.activeEditor && previewList.activeEditor !== newNameEdit) {
                                                    previewList.activeEditor.deselect()
                                                }
                                                previewList.activeEditor = newNameEdit
                                            } else if (!textContextMenu.visible) {
                                                deselect()
                                            }
                                        }
                                        onSelectedTextChanged: {
                                            if (selectedText.length > 0) {
                                                previewList.activeEditor = newNameEdit
                                            }
                                        }
                                        QQC2.ToolTip.visible: rowDelegate.hovered && rowDelegate.newName !== rowDelegate.originalName && selectedText.length === 0
                                        QQC2.ToolTip.delay: 600
                                        QQC2.ToolTip.text: rowDelegate.newName

                                        MouseArea {
                                            anchors.fill: parent
                                            acceptedButtons: Qt.RightButton
                                            cursorShape: Qt.IBeamCursor
                                            onClicked: {
                                                newNameEdit.forceActiveFocus()
                                                textContextMenu.targetEditor = newNameEdit
                                                textContextMenu.popup()
                                            }
                                        }
                                    }

                                    // Status Badge / Message (quiet when unchanged, highlighted when changed/error)
                                    RowLayout {
                                        Layout.preferredWidth: tableContainer.statusColWidth
                                        Layout.maximumWidth: tableContainer.statusColWidth
                                        Layout.alignment: Qt.AlignVCenter
                                        spacing: 4

                                        Kirigami.Icon {
                                            Layout.preferredWidth: Kirigami.Units.iconSizes.small
                                            Layout.preferredHeight: Kirigami.Units.iconSizes.small
                                            visible: rowDelegate.status !== "unchanged"
                                            source: {
                                                if (rowDelegate.status === "ready") return "dialog-ok-apply"
                                                if (rowDelegate.status === "renamed") return "emblem-checked"
                                                if (rowDelegate.status === "conflict" || rowDelegate.status === "invalid" || rowDelegate.status === "error")
                                                    return "dialog-error"
                                                return ""
                                            }
                                        }

                                        QQC2.Label {
                                            Layout.fillWidth: true
                                            elide: Text.ElideRight
                                            font.pointSize: Kirigami.Theme.smallFont.pointSize
                                            text: {
                                                if (rowDelegate.errorMessage !== "") return rowDelegate.errorMessage
                                                if (rowDelegate.status === "ready") return qsTr("Ready")
                                                if (rowDelegate.status === "renamed") return qsTr("Renamed")
                                                return qsTr("—")
                                            }
                                            opacity: rowDelegate.status === "unchanged" ? 0.4 : 1.0
                                            color: {
                                                if (rowDelegate.status === "conflict" || rowDelegate.status === "invalid" || rowDelegate.status === "error")
                                                    return Kirigami.Theme.negativeTextColor
                                                if (rowDelegate.status === "ready" || rowDelegate.status === "renamed")
                                                    return Kirigami.Theme.positiveTextColor
                                                return Kirigami.Theme.disabledTextColor
                                            }
                                            QQC2.ToolTip.visible: rowDelegate.hovered && rowDelegate.errorMessage !== ""
                                            QQC2.ToolTip.text: rowDelegate.errorMessage
                                        }
                                    }

                                    // Remove row button (visible on row hover to eliminate red-X visual noise)
                                    QQC2.ToolButton {
                                        Layout.preferredWidth: tableContainer.actionColWidth
                                        Layout.maximumWidth: tableContainer.actionColWidth
                                        Layout.preferredHeight: Kirigami.Units.iconSizes.smallMedium
                                        padding: 0
                                        flat: true
                                        opacity: rowDelegate.hovered ? 0.85 : 0.0
                                        icon.name: "edit-delete-remove"
                                        icon.width: Kirigami.Units.iconSizes.small
                                        icon.height: Kirigami.Units.iconSizes.small
                                        display: QQC2.AbstractButton.IconOnly
                                        QQC2.ToolTip.visible: hovered
                                        QQC2.ToolTip.text: qsTr("Remove from list")
                                        onClicked: renamerController.removeItem(rowDelegate.index)
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    // --- Keyboard Shortcuts Dialog ---
    Kirigami.Dialog {
        id: shortcutsDialog
        title: qsTr("Keyboard Shortcuts")
        standardButtons: Kirigami.Dialog.NoButton
        preferredWidth: 440
        maximumWidth: 440

        Item {
            implicitWidth: 440
            implicitHeight: shortcutsCol.implicitHeight + (Kirigami.Units.largeSpacing * 2)

            ColumnLayout {
                id: shortcutsCol
                anchors.fill: parent
                anchors.margins: Kirigami.Units.largeSpacing
                spacing: Kirigami.Units.mediumSpacing

                Repeater {
                    model: [
                        { keys: "Ctrl+O", desc: qsTr("Add files to the list") },
                        { keys: "Ctrl+Shift+O", desc: qsTr("Add a folder to the list") },
                        { keys: "Ctrl+Z", desc: qsTr("Undo the last batch rename") },
                        { keys: "Ctrl+C", desc: qsTr("Copy highlighted filename text") },
                        { keys: "Ctrl+?", desc: qsTr("Show keyboard shortcuts") },
                        { keys: "Tab / Shift+Tab", desc: qsTr("Move focus between sidebar controls") },
                        { keys: "Double-Click (Folder Icon)", desc: qsTr("Expand or collapse folder in tree") }
                    ]

                    delegate: RowLayout {
                        required property var modelData
                        Layout.fillWidth: true
                        spacing: Kirigami.Units.largeSpacing

                        QQC2.Label {
                            text: modelData.desc
                            Layout.fillWidth: true
                            wrapMode: Text.WordWrap
                        }

                        Rectangle {
                            radius: Kirigami.Units.smallSpacing
                            color: Kirigami.Theme.alternateBackgroundColor
                            border.color: Qt.rgba(Kirigami.Theme.textColor.r,
                                                  Kirigami.Theme.textColor.g,
                                                  Kirigami.Theme.textColor.b, 0.25)
                            border.width: 1
                            implicitWidth: keyLabel.implicitWidth + (Kirigami.Units.mediumSpacing * 2)
                            implicitHeight: keyLabel.implicitHeight + Kirigami.Units.smallSpacing

                            QQC2.Label {
                                id: keyLabel
                                anchors.centerIn: parent
                                text: modelData.keys
                                font.family: "monospace"
                                font.pointSize: Kirigami.Theme.smallFont.pointSize
                                font.bold: true
                            }
                        }
                    }
                }
            }
        }
    }

    // --- About Dialog ---
    Kirigami.Dialog {
        id: aboutDialog
        title: qsTr("About Namr")
        standardButtons: Kirigami.Dialog.NoButton
        preferredWidth: 360
        maximumWidth: 360

        Item {
            implicitWidth: 360
            implicitHeight: aboutCol.implicitHeight + (Kirigami.Units.largeSpacing * 2)

            ColumnLayout {
                id: aboutCol
                anchors.fill: parent
                anchors.margins: Kirigami.Units.largeSpacing
                spacing: Kirigami.Units.mediumSpacing

                RowLayout {
                    Layout.fillWidth: true
                    spacing: Kirigami.Units.largeSpacing

                    Kirigami.Icon {
                        source: "fans.bingus.namr"
                        fallback: "edit-rename"
                        Layout.preferredWidth: Kirigami.Units.iconSizes.huge
                        Layout.preferredHeight: Kirigami.Units.iconSizes.huge
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 2

                        Kirigami.Heading {
                            level: 2
                            text: qsTr("Namr")
                        }

                        QQC2.Label {
                            text: qsTr("Version %1").arg(renamerController.appVersion)
                            opacity: 0.75
                        }

                        QQC2.Label {
                            text: "fans.bingus.namr"
                            font.pointSize: Kirigami.Theme.smallFont.pointSize
                            opacity: 0.55
                        }
                    }
                }

                Kirigami.Separator {
                    Layout.fillWidth: true
                }

                QQC2.Label {
                    Layout.fillWidth: true
                    wrapMode: Text.WordWrap
                    text: qsTr("A modern bulk file and folder renamer for KDE Plasma 6 with live diff previews, hierarchical tree browsing, conflict validation, and undo support.")
                }

                QQC2.Label {
                    Layout.fillWidth: true
                    wrapMode: Text.WordWrap
                    font.pointSize: Kirigami.Theme.smallFont.pointSize
                    opacity: 0.8
                    text: qsTr("License: Public Domain (The Unlicense)")
                }

                QQC2.Label {
                    Layout.fillWidth: true
                    textFormat: Text.RichText
                    text: "<a href=\"https://github.com/louis-irl/namr\" style=\"color: " + Kirigami.Theme.linkColor + ";\">https://github.com/louis-irl/namr</a>"
                    onLinkActivated: function(link) {
                        Qt.openUrlExternally(link)
                    }
                    HoverHandler {
                        cursorShape: parent.hoveredLink ? Qt.PointingHandCursor : Qt.ArrowCursor
                    }
                }
            }
        }
    }
}
