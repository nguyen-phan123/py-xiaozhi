// 快捷键设置页
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../../theme"
import "../../controls"

ScrollView {
    id: root
    clip: true

    ColumnLayout {
        width: root.availableWidth
        spacing: Theme.spacingLg

        // 页面标题
        Text {
            text: "Cài đặt phím tắt"
            font.pixelSize: Theme.fontSizeXl
            font.weight: Font.DemiBold
            color: Theme.textPrimary
        }

        // 基本设置
        ColumnLayout {
            Layout.fillWidth: true
            spacing: Theme.spacingMd

            Text {
                text: "Cài đặt cơ bản"
                font.pixelSize: Theme.fontSizeMd
                font.weight: Font.Medium
                color: Theme.textSecondary
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.spacingMd

                Text {
                    text: "Bật phím tắt toàn cục"
                    font.pixelSize: Theme.fontSizeSm
                    color: Theme.textSecondary
                }

                Item { Layout.fillWidth: true }

                XSwitch {
                    checked: settingsModel ? settingsModel.shortcutsEnabled : false
                    onToggled: if (settingsModel) settingsModel.shortcutsEnabled = checked
                }
            }
        }

        // 分隔线
        Rectangle {
            Layout.fillWidth: true
            height: 1
            color: Theme.divider
        }

        // 快捷键配置
        ColumnLayout {
            Layout.fillWidth: true
            spacing: Theme.spacingMd
            opacity: settingsModel && settingsModel.shortcutsEnabled ? 1.0 : 0.5
            enabled: settingsModel ? settingsModel.shortcutsEnabled : false

            Text {
                text: "Cấu hình phím tắt"
                font.pixelSize: Theme.fontSizeMd
                font.weight: Font.Medium
                color: Theme.textSecondary
            }

            // 按住说话
            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.spacingMd

                Text {
                    text: "Nhấn giữ để nói"
                    font.pixelSize: Theme.fontSizeSm
                    color: Theme.textPrimary
                    Layout.preferredWidth: 80
                }

                XComboBox {
                    id: manualModCombo
                    Layout.preferredWidth: 100
                    model: ["Ctrl", "Alt", "Shift", "Cmd"]
                    currentIndex: {
                        var mod = settingsModel ? settingsModel.shortcutManualModifier : "ctrl"
                        if (mod === "alt") return 1
                        if (mod === "shift") return 2
                        if (mod === "cmd") return 3
                        return 0  // ctrl
                    }
                    onActivated: function(index) {
                        var options = ["ctrl", "alt", "shift", "cmd"]
                        if (settingsModel) settingsModel.shortcutManualModifier = options[index]
                    }
                }

                Text { text: "+"; font.pixelSize: Theme.fontSizeSm; color: Theme.textSecondary }

                TextField {
                    id: manualKeyField
                    Layout.preferredWidth: 50
                    text: settingsModel ? settingsModel.shortcutManualKey : ""
                    onEditingFinished: if (settingsModel) settingsModel.shortcutManualKey = text.toLowerCase()
                    maximumLength: 1
                    horizontalAlignment: Text.AlignHCenter
                    font.pixelSize: Theme.fontSizeSm
                    background: Rectangle {
                        radius: Theme.radiusSm
                        color: Theme.backgroundSecondary
                        border.color: manualKeyField.activeFocus ? Theme.primary : "transparent"
                    }
                }

                Text {
                    Layout.fillWidth: true
                    text: "Nhấn giữ để ghi âm"
                    font.pixelSize: Theme.fontSizeSm
                    color: Theme.textPlaceholder
                }
            }

            Rectangle { Layout.fillWidth: true; height: 1; color: Theme.divider }

            // 自动对话
            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.spacingMd

                Text {
                    text: "Hội thoại tự động"
                    font.pixelSize: Theme.fontSizeSm
                    color: Theme.textPrimary
                    Layout.preferredWidth: 80
                }

                XComboBox {
                    id: autoModCombo
                    Layout.preferredWidth: 100
                    model: ["Ctrl", "Alt", "Shift", "Cmd"]
                    currentIndex: {
                        var mod = settingsModel ? settingsModel.shortcutAutoModifier : "ctrl"
                        if (mod === "alt") return 1
                        if (mod === "shift") return 2
                        if (mod === "cmd") return 3
                        return 0
                    }
                    onActivated: function(index) {
                        var options = ["ctrl", "alt", "shift", "cmd"]
                        if (settingsModel) settingsModel.shortcutAutoModifier = options[index]
                    }
                }

                Text { text: "+"; font.pixelSize: Theme.fontSizeSm; color: Theme.textSecondary }

                TextField {
                    id: autoKeyField
                    Layout.preferredWidth: 50
                    text: settingsModel ? settingsModel.shortcutAutoKey : ""
                    onEditingFinished: if (settingsModel) settingsModel.shortcutAutoKey = text.toLowerCase()
                    maximumLength: 1
                    horizontalAlignment: Text.AlignHCenter
                    font.pixelSize: Theme.fontSizeSm
                    background: Rectangle {
                        radius: Theme.radiusSm
                        color: Theme.backgroundSecondary
                        border.color: autoKeyField.activeFocus ? Theme.primary : "transparent"
                    }
                }

                Text {
                    Layout.fillWidth: true
                    text: "Bật/Tắt hội thoại tự động"
                    font.pixelSize: Theme.fontSizeSm
                    color: Theme.textPlaceholder
                }
            }

            Rectangle { Layout.fillWidth: true; height: 1; color: Theme.divider }

            // 中断对话
            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.spacingMd

                Text {
                    text: "Ngắt lời hội thoại"
                    font.pixelSize: Theme.fontSizeSm
                    color: Theme.textPrimary
                    Layout.preferredWidth: 80
                }

                XComboBox {
                    id: abortModCombo
                    Layout.preferredWidth: 100
                    model: ["Ctrl", "Alt", "Shift", "Cmd"]
                    currentIndex: {
                        var mod = settingsModel ? settingsModel.shortcutAbortModifier : "ctrl"
                        if (mod === "alt") return 1
                        if (mod === "shift") return 2
                        if (mod === "cmd") return 3
                        return 0
                    }
                    onActivated: function(index) {
                        var options = ["ctrl", "alt", "shift", "cmd"]
                        if (settingsModel) settingsModel.shortcutAbortModifier = options[index]
                    }
                }

                Text { text: "+"; font.pixelSize: Theme.fontSizeSm; color: Theme.textSecondary }

                TextField {
                    id: abortKeyField
                    Layout.preferredWidth: 50
                    text: settingsModel ? settingsModel.shortcutAbortKey : ""
                    onEditingFinished: if (settingsModel) settingsModel.shortcutAbortKey = text.toLowerCase()
                    maximumLength: 1
                    horizontalAlignment: Text.AlignHCenter
                    font.pixelSize: Theme.fontSizeSm
                    background: Rectangle {
                        radius: Theme.radiusSm
                        color: Theme.backgroundSecondary
                        border.color: abortKeyField.activeFocus ? Theme.primary : "transparent"
                    }
                }

                Text {
                    Layout.fillWidth: true
                    text: "Dừng ngay hội thoại hiện tại"
                    font.pixelSize: Theme.fontSizeSm
                    color: Theme.textPlaceholder
                }
            }

            Rectangle { Layout.fillWidth: true; height: 1; color: Theme.divider }

            // 切换模式
            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.spacingMd

                Text {
                    text: "Chuyển chế độ"
                    font.pixelSize: Theme.fontSizeSm
                    color: Theme.textPrimary
                    Layout.preferredWidth: 80
                }

                XComboBox {
                    id: modeModCombo
                    Layout.preferredWidth: 100
                    model: ["Ctrl", "Alt", "Shift", "Cmd"]
                    currentIndex: {
                        var mod = settingsModel ? settingsModel.shortcutModeModifier : "ctrl"
                        if (mod === "alt") return 1
                        if (mod === "shift") return 2
                        if (mod === "cmd") return 3
                        return 0
                    }
                    onActivated: function(index) {
                        var options = ["ctrl", "alt", "shift", "cmd"]
                        if (settingsModel) settingsModel.shortcutModeModifier = options[index]
                    }
                }

                Text { text: "+"; font.pixelSize: Theme.fontSizeSm; color: Theme.textSecondary }

                TextField {
                    id: modeKeyField
                    Layout.preferredWidth: 50
                    text: settingsModel ? settingsModel.shortcutModeKey : ""
                    onEditingFinished: if (settingsModel) settingsModel.shortcutModeKey = text.toLowerCase()
                    maximumLength: 1
                    horizontalAlignment: Text.AlignHCenter
                    font.pixelSize: Theme.fontSizeSm
                    background: Rectangle {
                        radius: Theme.radiusSm
                        color: Theme.backgroundSecondary
                        border.color: modeKeyField.activeFocus ? Theme.primary : "transparent"
                    }
                }

                Text {
                    Layout.fillWidth: true
                    text: "Chuyển đổi thủ công / tự động"
                    font.pixelSize: Theme.fontSizeSm
                    color: Theme.textPlaceholder
                }
            }

            Rectangle { Layout.fillWidth: true; height: 1; color: Theme.divider }

            // 显示/隐藏窗口
            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.spacingMd

                Text {
                    text: "Hiện/Ẩn"
                    font.pixelSize: Theme.fontSizeSm
                    color: Theme.textPrimary
                    Layout.preferredWidth: 80
                }

                XComboBox {
                    id: windowModCombo
                    Layout.preferredWidth: 100
                    model: ["Ctrl", "Alt", "Shift", "Cmd"]
                    currentIndex: {
                        var mod = settingsModel ? settingsModel.shortcutWindowModifier : "ctrl"
                        if (mod === "alt") return 1
                        if (mod === "shift") return 2
                        if (mod === "cmd") return 3
                        return 0
                    }
                    onActivated: function(index) {
                        var options = ["ctrl", "alt", "shift", "cmd"]
                        if (settingsModel) settingsModel.shortcutWindowModifier = options[index]
                    }
                }

                Text { text: "+"; font.pixelSize: Theme.fontSizeSm; color: Theme.textSecondary }

                TextField {
                    id: windowKeyField
                    Layout.preferredWidth: 50
                    text: settingsModel ? settingsModel.shortcutWindowKey : ""
                    onEditingFinished: if (settingsModel) settingsModel.shortcutWindowKey = text.toLowerCase()
                    maximumLength: 1
                    horizontalAlignment: Text.AlignHCenter
                    font.pixelSize: Theme.fontSizeSm
                    background: Rectangle {
                        radius: Theme.radiusSm
                        color: Theme.backgroundSecondary
                        border.color: windowKeyField.activeFocus ? Theme.primary : "transparent"
                    }
                }

                Text {
                    Layout.fillWidth: true
                    text: "Bật/Tắt hiển thị cửa sổ chính"
                    font.pixelSize: Theme.fontSizeSm
                    color: Theme.textPlaceholder
                }
            }
        }

        // 分隔线
        Rectangle {
            Layout.fillWidth: true
            height: 1
            color: Theme.divider
        }

        // 提示信息
        Text {
            Layout.fillWidth: true
            text: "Phím tắt có hiệu lực toàn cục trên hệ thống. Vui lòng đảm bảo không xung đột với ứng dụng khác."
            font.pixelSize: Theme.fontSizeSm
            color: Theme.textPlaceholder
            wrapMode: Text.WordWrap
        }

        Item { Layout.fillHeight: true }
    }
}
