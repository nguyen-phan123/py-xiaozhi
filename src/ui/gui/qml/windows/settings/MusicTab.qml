// 音乐设置页
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

        Text {
            text: "Cấu hình âm nhạc"
            font.pixelSize: Theme.fontSizeXl
            font.weight: Font.DemiBold
            color: Theme.textPrimary
        }

        // API 配置
        ColumnLayout {
            Layout.fillWidth: true
            spacing: Theme.spacingMd

            Text {
                text: "Cài đặt API"
                font.pixelSize: Theme.fontSizeMd
                font.weight: Font.Medium
                color: Theme.textSecondary
            }

            GridLayout {
                Layout.fillWidth: true
                columns: 2
                rowSpacing: Theme.spacingMd
                columnSpacing: Theme.spacingLg

                Text {
                    text: "API tìm kiếm"
                    font.pixelSize: Theme.fontSizeSm
                    color: Theme.textSecondary
                    Layout.preferredWidth: 120
                }
                TextField {
                    id: musicSearchUrlField
                    Layout.fillWidth: true
                    text: settingsModel ? settingsModel.musicSearchUrl : ""
                    // 边改边写回；只靠 editingFinished 时点保存常写不上空串
                    onTextEdited: if (settingsModel) settingsModel.musicSearchUrl = text
                    onEditingFinished: if (settingsModel) settingsModel.musicSearchUrl = text
                    placeholderText: "Để trống dùng API tìm kiếm Kuwo mặc định"
                    font.pixelSize: Theme.fontSizeSm
                    background: Rectangle {
                        radius: Theme.radiusSm
                        color: Theme.backgroundSecondary
                        border.color: musicSearchUrlField.activeFocus ? Theme.primary : "transparent"
                    }
                }

                Text {
                    text: "API link trực tiếp"
                    font.pixelSize: Theme.fontSizeSm
                    color: Theme.textSecondary
                    Layout.preferredWidth: 120
                }
                TextField {
                    id: musicUrlApiField
                    Layout.fillWidth: true
                    text: settingsModel ? settingsModel.musicUrlApi : ""
                    onTextEdited: if (settingsModel) settingsModel.musicUrlApi = text
                    onEditingFinished: if (settingsModel) settingsModel.musicUrlApi = text
                    placeholderText: "Để trống dùng lx-music-api mặc định"
                    font.pixelSize: Theme.fontSizeSm
                    background: Rectangle {
                        radius: Theme.radiusSm
                        color: Theme.backgroundSecondary
                        border.color: musicUrlApiField.activeFocus ? Theme.primary : "transparent"
                    }
                }

                Text {
                    text: "API Key"
                    font.pixelSize: Theme.fontSizeSm
                    color: Theme.textSecondary
                    Layout.preferredWidth: 120
                }
                TextField {
                    id: musicUrlApiKeyField
                    Layout.fillWidth: true
                    text: settingsModel ? settingsModel.musicUrlApiKey : ""
                    onTextEdited: if (settingsModel) settingsModel.musicUrlApiKey = text
                    onEditingFinished: if (settingsModel) settingsModel.musicUrlApiKey = text
                    placeholderText: "Để trống dùng Key mặc định"
                    font.pixelSize: Theme.fontSizeSm
                    background: Rectangle {
                        radius: Theme.radiusSm
                        color: Theme.backgroundSecondary
                        border.color: musicUrlApiKeyField.activeFocus ? Theme.primary : "transparent"
                    }
                }
            }

            Text {
                text: "API tìm kiếm dùng cổng chính thức Kuwo, API link trực tiếp để lấy URL phát nhạc (cần API Key)"
                font.pixelSize: Theme.fontSizeXs
                color: Theme.textPlaceholder
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
        }

        Rectangle {
            Layout.fillWidth: true
            height: 1
            color: Theme.divider
        }

        // 播放偏好
        ColumnLayout {
            Layout.fillWidth: true
            spacing: Theme.spacingMd

            Text {
                text: "Tùy chọn phát"
                font.pixelSize: Theme.fontSizeMd
                font.weight: Font.Medium
                color: Theme.textSecondary
            }

            GridLayout {
                Layout.fillWidth: true
                columns: 2
                rowSpacing: Theme.spacingMd
                columnSpacing: Theme.spacingLg

                Text {
                    text: "Chất lượng mặc định"
                    font.pixelSize: Theme.fontSizeSm
                    color: Theme.textSecondary
                    Layout.preferredWidth: 120
                }
                XComboBox {
                    id: musicQualityCombo
                    Layout.preferredWidth: 150
                    model: ["128k", "320k"]
                    currentIndex: {
                        var q = settingsModel ? settingsModel.musicDefaultQuality : "320k"
                        var idx = ["128k", "320k"].indexOf(q)
                        return idx >= 0 ? idx : 1
                    }
                    onActivated: function(index) {
                        if (settingsModel) settingsModel.musicDefaultQuality = model[index]
                    }
                    font.pixelSize: Theme.fontSizeSm
                }
            }
        }

        Item { Layout.fillHeight: true }
    }
}
