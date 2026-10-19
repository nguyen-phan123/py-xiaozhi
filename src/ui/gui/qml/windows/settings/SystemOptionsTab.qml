// Cài đặt tùy chọn hệ thống
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

        // Tiêu đề trang
        Text {
            text: "Tùy chọn hệ thống"
            font.pixelSize: Theme.fontSizeXl
            font.weight: Font.DemiBold
            color: Theme.textPrimary
        }

        // Khu vực thông tin cơ bản
        ColumnLayout {
            Layout.fillWidth: true
            spacing: Theme.spacingMd

            // Tiêu đề khu vực
            Text {
                text: "Thông tin cơ bản"
                font.pixelSize: Theme.fontSizeMd
                font.weight: Font.Medium
                color: Theme.textSecondary
            }

            // Các mục biểu mẫu
            GridLayout {
                Layout.fillWidth: true
                columns: 2
                rowSpacing: Theme.spacingMd
                columnSpacing: Theme.spacingLg

                Text {
                    text: "ID máy khách"
                    font.pixelSize: Theme.fontSizeSm
                    color: Theme.textSecondary
                    Layout.preferredWidth: 100
                }
                TextField {
                    id: clientIdField
                    Layout.fillWidth: true
                    text: settingsModel ? settingsModel.clientId : ""
                    onEditingFinished: if (settingsModel) settingsModel.clientId = text
                    placeholderText: "Tự động tạo"
                    font.pixelSize: Theme.fontSizeSm
                    background: Rectangle {
                        radius: Theme.radiusSm
                        color: Theme.backgroundSecondary
                        border.color: clientIdField.activeFocus ? Theme.primary : "transparent"
                    }
                }

                Text {
                    text: "ID thiết bị"
                    font.pixelSize: Theme.fontSizeSm
                    color: Theme.textSecondary
                    Layout.preferredWidth: 100
                }
                TextField {
                    id: deviceIdField
                    Layout.fillWidth: true
                    text: settingsModel ? settingsModel.deviceId : ""
                    onEditingFinished: if (settingsModel) settingsModel.deviceId = text
                    placeholderText: "Tự động tạo"
                    font.pixelSize: Theme.fontSizeSm
                    background: Rectangle {
                        radius: Theme.radiusSm
                        color: Theme.backgroundSecondary
                        border.color: deviceIdField.activeFocus ? Theme.primary : "transparent"
                    }
                }

            }
        }

        // Đường phân cách
        Rectangle {
            Layout.fillWidth: true
            height: 1
            color: Theme.divider
        }

        // Khu vực khử tiếng vang
        ColumnLayout {
            Layout.fillWidth: true
            spacing: Theme.spacingMd

            Text {
                text: "Khử tiếng vang"
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
                    text: "Bật"
                    font.pixelSize: Theme.fontSizeSm
                    color: Theme.textSecondary
                    Layout.preferredWidth: 100
                }
                XSwitch {
                    id: aecEnabledSwitch
                    checked: settingsModel ? settingsModel.aecEnabled : false
                    onToggled: if (settingsModel) settingsModel.aecEnabled = checked
                }

                Text {
                    text: "Phát nhạc song song"
                    font.pixelSize: Theme.fontSizeSm
                    color: Theme.textSecondary
                    Layout.preferredWidth: 100
                    opacity: aecEnabledSwitch.checked ? 1 : 0.45
                }
                XSwitch {
                    enabled: aecEnabledSwitch.checked
                    opacity: aecEnabledSwitch.checked ? 1 : 0.45
                    checked: settingsModel ? settingsModel.aecMusicParallel : true
                    onToggled: if (settingsModel) settingsModel.aecMusicParallel = checked
                }

                Text {
                    text: "Số khung bù trễ"
                    font.pixelSize: Theme.fontSizeSm
                    color: Theme.textSecondary
                    Layout.preferredWidth: 100
                    opacity: aecEnabledSwitch.checked ? 1 : 0.45
                }
                XSpinBox {
                    Layout.preferredWidth: 120
                    enabled: aecEnabledSwitch.checked
                    opacity: aecEnabledSwitch.checked ? 1 : 0.45
                    from: 0
                    to: 20
                    value: settingsModel ? settingsModel.aecFrameDelay : 3
                    onValueModified: if (settingsModel) settingsModel.aecFrameDelay = value
                    font.pixelSize: Theme.fontSizeSm
                }

                Text {
                    text: "Tiền xử lý giảm ồn"
                    font.pixelSize: Theme.fontSizeSm
                    color: Theme.textSecondary
                    Layout.preferredWidth: 100
                    opacity: aecEnabledSwitch.checked ? 1 : 0.45
                }
                XSwitch {
                    enabled: aecEnabledSwitch.checked
                    opacity: aecEnabledSwitch.checked ? 1 : 0.45
                    checked: settingsModel ? settingsModel.aecEnablePreprocess : true
                    onToggled: if (settingsModel) settingsModel.aecEnablePreprocess = checked
                }
            }

            Text {
                Layout.fillWidth: true
                text: "Khử tiếng vang TTS/âm nhạc của ứng dụng, bật để vào chế độ đàm thoại thời gian thực; Phát nhạc song song = giảm âm lượng nhạc thay vì tạm dừng khi phát TTS; Bù độ trễ = 40ms + N × độ dài khung giao thức, thiết bị Bluetooth có thể tăng lên một cách thích hợp. Khởi động lại ứng dụng để có hiệu lực."
                font.pixelSize: Theme.fontSizeXs
                color: Theme.textSecondary
                wrapMode: Text.WordWrap
            }
        }

        // Đường phân cách
        Rectangle {
            Layout.fillWidth: true
            height: 1
            color: Theme.divider
        }

        // Khu vực cấu hình mạng
        ColumnLayout {
            Layout.fillWidth: true
            spacing: Theme.spacingMd

            Text {
                text: "Cấu hình mạng"
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
                    text: "WebSocket URL"
                    font.pixelSize: Theme.fontSizeSm
                    color: Theme.textSecondary
                    Layout.preferredWidth: 100
                }
                TextField {
                    id: wsUrlField
                    Layout.fillWidth: true
                    text: settingsModel ? settingsModel.websocketUrl : ""
                    onEditingFinished: if (settingsModel) settingsModel.websocketUrl = text
                    placeholderText: "wss://..."
                    font.pixelSize: Theme.fontSizeSm
                    background: Rectangle {
                        radius: Theme.radiusSm
                        color: Theme.backgroundSecondary
                        border.color: wsUrlField.activeFocus ? Theme.primary : "transparent"
                    }
                }

                Text {
                    text: "Access Token"
                    font.pixelSize: Theme.fontSizeSm
                    color: Theme.textSecondary
                    Layout.preferredWidth: 100
                }
                XTextField {
                    id: wsTokenField
                    Layout.fillWidth: true
                    text: settingsModel ? settingsModel.websocketToken : ""
                    onEditingFinished: if (settingsModel) settingsModel.websocketToken = text
                    isPassword: true
                }

                Text {
                    text: "URL phiên bản OTA"
                    font.pixelSize: Theme.fontSizeSm
                    color: Theme.textSecondary
                    Layout.preferredWidth: 100
                }
                TextField {
                    id: otaUrlField
                    Layout.fillWidth: true
                    text: settingsModel ? settingsModel.otaUrl : ""
                    onEditingFinished: if (settingsModel) settingsModel.otaUrl = text
                    font.pixelSize: Theme.fontSizeSm
                    background: Rectangle {
                        radius: Theme.radiusSm
                        color: Theme.backgroundSecondary
                        border.color: otaUrlField.activeFocus ? Theme.primary : "transparent"
                    }
                }

                Text {
                    text: "URL ủy quyền"
                    font.pixelSize: Theme.fontSizeSm
                    color: Theme.textSecondary
                    Layout.preferredWidth: 100
                }
                TextField {
                    id: authUrlField
                    Layout.fillWidth: true
                    text: settingsModel ? settingsModel.authorizationUrl : ""
                    onEditingFinished: if (settingsModel) settingsModel.authorizationUrl = text
                    font.pixelSize: Theme.fontSizeSm
                    background: Rectangle {
                        radius: Theme.radiusSm
                        color: Theme.backgroundSecondary
                        border.color: authUrlField.activeFocus ? Theme.primary : "transparent"
                    }
                }

                Text {
                    text: "Phiên bản kích hoạt"
                    font.pixelSize: Theme.fontSizeSm
                    color: Theme.textSecondary
                    Layout.preferredWidth: 100
                }
                XComboBox {
                    id: activationCombo
                    Layout.preferredWidth: 120
                    model: ["v1", "v2"]
                    currentIndex: settingsModel && settingsModel.activationVersion === "v2" ? 1 : 0
                    onActivated: function(index) {
                        if (settingsModel) settingsModel.activationVersion = index === 1 ? "v2" : "v1"
                    }
                    font.pixelSize: Theme.fontSizeSm
                }
            }
        }

        // Đường phân cách
        Rectangle {
            Layout.fillWidth: true
            height: 1
            color: Theme.divider
        }

        // Khu vực cấu hình MQTT
        ColumnLayout {
            Layout.fillWidth: true
            spacing: Theme.spacingMd

            Text {
                text: "Cấu hình MQTT"
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
                    text: "Endpoint máy chủ"
                    font.pixelSize: Theme.fontSizeSm
                    color: Theme.textSecondary
                    Layout.preferredWidth: 100
                }
                TextField {
                    id: mqttEndpointField
                    Layout.fillWidth: true
                    text: settingsModel ? settingsModel.mqttEndpoint : ""
                    onEditingFinished: if (settingsModel) settingsModel.mqttEndpoint = text
                    placeholderText: "mqtt.example.com"
                    font.pixelSize: Theme.fontSizeSm
                    background: Rectangle {
                        radius: Theme.radiusSm
                        color: Theme.backgroundSecondary
                        border.color: mqttEndpointField.activeFocus ? Theme.primary : "transparent"
                    }
                }

                Text {
                    text: "ID máy khách"
                    font.pixelSize: Theme.fontSizeSm
                    color: Theme.textSecondary
                    Layout.preferredWidth: 100
                }
                TextField {
                    id: mqttClientIdField
                    Layout.fillWidth: true
                    text: settingsModel ? settingsModel.mqttClientId : ""
                    onEditingFinished: if (settingsModel) settingsModel.mqttClientId = text
                    font.pixelSize: Theme.fontSizeSm
                    background: Rectangle {
                        radius: Theme.radiusSm
                        color: Theme.backgroundSecondary
                        border.color: mqttClientIdField.activeFocus ? Theme.primary : "transparent"
                    }
                }

                Text {
                    text: "Tên người dùng"
                    font.pixelSize: Theme.fontSizeSm
                    color: Theme.textSecondary
                    Layout.preferredWidth: 100
                }
                TextField {
                    id: mqttUsernameField
                    Layout.fillWidth: true
                    text: settingsModel ? settingsModel.mqttUsername : ""
                    onEditingFinished: if (settingsModel) settingsModel.mqttUsername = text
                    font.pixelSize: Theme.fontSizeSm
                    background: Rectangle {
                        radius: Theme.radiusSm
                        color: Theme.backgroundSecondary
                        border.color: mqttUsernameField.activeFocus ? Theme.primary : "transparent"
                    }
                }

                Text {
                    text: "Mật khẩu"
                    font.pixelSize: Theme.fontSizeSm
                    color: Theme.textSecondary
                    Layout.preferredWidth: 100
                }
                XTextField {
                    id: mqttPasswordField
                    Layout.fillWidth: true
                    text: settingsModel ? settingsModel.mqttPassword : ""
                    onEditingFinished: if (settingsModel) settingsModel.mqttPassword = text
                    isPassword: true
                }

                Text {
                    text: "Topic xuất bản"
                    font.pixelSize: Theme.fontSizeSm
                    color: Theme.textSecondary
                    Layout.preferredWidth: 100
                }
                TextField {
                    id: mqttPubField
                    Layout.fillWidth: true
                    text: settingsModel ? settingsModel.mqttPublishTopic : ""
                    onEditingFinished: if (settingsModel) settingsModel.mqttPublishTopic = text
                    font.pixelSize: Theme.fontSizeSm
                    background: Rectangle {
                        radius: Theme.radiusSm
                        color: Theme.backgroundSecondary
                        border.color: mqttPubField.activeFocus ? Theme.primary : "transparent"
                    }
                }

                Text {
                    text: "Topic đăng ký"
                    font.pixelSize: Theme.fontSizeSm
                    color: Theme.textSecondary
                    Layout.preferredWidth: 100
                }
                TextField {
                    id: mqttSubField
                    Layout.fillWidth: true
                    text: settingsModel ? settingsModel.mqttSubscribeTopic : ""
                    onEditingFinished: if (settingsModel) settingsModel.mqttSubscribeTopic = text
                    font.pixelSize: Theme.fontSizeSm
                    background: Rectangle {
                        radius: Theme.radiusSm
                        color: Theme.backgroundSecondary
                        border.color: mqttSubField.activeFocus ? Theme.primary : "transparent"
                    }
                }
            }
        }

        // Đường phân cách
        Rectangle {
            Layout.fillWidth: true
            height: 1
            color: Theme.divider
        }

        // Thư mục dữ liệu
        ColumnLayout {
            Layout.fillWidth: true
            spacing: Theme.spacingMd

            Text {
                text: "Thư mục dữ liệu"
                font.pixelSize: Theme.fontSizeMd
                font.weight: Font.Medium
                color: Theme.textSecondary
            }

            Text {
                Layout.fillWidth: true
                text: "File cấu hình vẫn nằm trong thư mục dữ liệu người dùng. Nhấp vào 「Chọn」 để mở hộp thoại thư mục hệ thống; 「Mặc định」 để đặt về mặc định của hệ thống. Sau khi lưu, lần khởi động tiếp theo sẽ sao chép từ thư mục cũ sang đường dẫn mới."
                font.pixelSize: Theme.fontSizeXs
                color: Theme.textSecondary
                wrapMode: Text.WordWrap
            }

            // Cache
            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.spacingSm
                Text {
                    text: "Thư mục bộ nhớ đệm"
                    font.pixelSize: Theme.fontSizeSm
                    color: Theme.textSecondary
                    Layout.preferredWidth: 100
                }
                TextField {
                    id: pathCacheField
                    Layout.fillWidth: true
                    text: settingsModel ? settingsModel.pathCacheDir : ""
                    onTextEdited: if (settingsModel) settingsModel.pathCacheDir = text
                    onEditingFinished: if (settingsModel) settingsModel.pathCacheDir = text
                    placeholderText: settingsModel ? settingsModel.pathDefaultCacheDir : ""
                    font.pixelSize: Theme.fontSizeSm
                    background: Rectangle {
                        radius: Theme.radiusSm
                        color: Theme.backgroundSecondary
                        border.color: pathCacheField.activeFocus ? Theme.primary : "transparent"
                    }
                }
                Button {
                    text: "Chọn"
                    font.pixelSize: Theme.fontSizeSm
                    Layout.preferredWidth: 64
                    Layout.preferredHeight: 32
                    background: Rectangle {
                        radius: Theme.radiusSm
                        color: parent.pressed ? Theme.backgroundHover : Theme.backgroundSecondary
                        border.width: 1
                        border.color: Theme.divider
                    }
                    contentItem: Text {
                        text: parent.text
                        font.pixelSize: Theme.fontSizeSm
                        color: Theme.textPrimary
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                    onClicked: {
                        if (!settingsModel) return
                        var p = settingsModel.browseDirectory("cache")
                        if (p) pathCacheField.text = p
                    }
                }
                Button {
                    text: "Mặc định"
                    font.pixelSize: Theme.fontSizeSm
                    Layout.preferredWidth: 64
                    Layout.preferredHeight: 32
                    background: Rectangle {
                        radius: Theme.radiusSm
                        color: parent.pressed ? Theme.backgroundHover : Theme.backgroundSecondary
                        border.width: 1
                        border.color: Theme.divider
                    }
                    contentItem: Text {
                        text: parent.text
                        font.pixelSize: Theme.fontSizeSm
                        color: Theme.textPrimary
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                    onClicked: {
                        if (!settingsModel) return
                        settingsModel.clearPathDir("cache")
                        pathCacheField.text = ""
                    }
                }
            }

            // Logs
            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.spacingSm
                Text {
                    text: "Thư mục nhật ký"
                    font.pixelSize: Theme.fontSizeSm
                    color: Theme.textSecondary
                    Layout.preferredWidth: 100
                }
                TextField {
                    id: pathLogField
                    Layout.fillWidth: true
                    text: settingsModel ? settingsModel.pathLogDir : ""
                    onTextEdited: if (settingsModel) settingsModel.pathLogDir = text
                    onEditingFinished: if (settingsModel) settingsModel.pathLogDir = text
                    placeholderText: settingsModel ? settingsModel.pathDefaultLogDir : ""
                    font.pixelSize: Theme.fontSizeSm
                    background: Rectangle {
                        radius: Theme.radiusSm
                        color: Theme.backgroundSecondary
                        border.color: pathLogField.activeFocus ? Theme.primary : "transparent"
                    }
                }
                Button {
                    text: "Chọn"
                    font.pixelSize: Theme.fontSizeSm
                    Layout.preferredWidth: 64
                    Layout.preferredHeight: 32
                    background: Rectangle {
                        radius: Theme.radiusSm
                        color: parent.pressed ? Theme.backgroundHover : Theme.backgroundSecondary
                        border.width: 1
                        border.color: Theme.divider
                    }
                    contentItem: Text {
                        text: parent.text
                        font.pixelSize: Theme.fontSizeSm
                        color: Theme.textPrimary
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                    onClicked: {
                        if (!settingsModel) return
                        var p = settingsModel.browseDirectory("log")
                        if (p) pathLogField.text = p
                    }
                }
                Button {
                    text: "Mặc định"
                    font.pixelSize: Theme.fontSizeSm
                    Layout.preferredWidth: 64
                    Layout.preferredHeight: 32
                    background: Rectangle {
                        radius: Theme.radiusSm
                        color: parent.pressed ? Theme.backgroundHover : Theme.backgroundSecondary
                        border.width: 1
                        border.color: Theme.divider
                    }
                    contentItem: Text {
                        text: parent.text
                        font.pixelSize: Theme.fontSizeSm
                        color: Theme.textPrimary
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                    onClicked: {
                        if (!settingsModel) return
                        settingsModel.clearPathDir("log")
                        pathLogField.text = ""
                    }
                }
            }

            // Music
            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.spacingSm
                Text {
                    text: "Bộ nhớ đệm âm nhạc"
                    font.pixelSize: Theme.fontSizeSm
                    color: Theme.textSecondary
                    Layout.preferredWidth: 100
                }
                TextField {
                    id: pathMusicField
                    Layout.fillWidth: true
                    text: settingsModel ? settingsModel.pathMusicCacheDir : ""
                    onTextEdited: if (settingsModel) settingsModel.pathMusicCacheDir = text
                    onEditingFinished: if (settingsModel) settingsModel.pathMusicCacheDir = text
                    placeholderText: settingsModel ? settingsModel.pathDefaultMusicCacheDir : ""
                    font.pixelSize: Theme.fontSizeSm
                    background: Rectangle {
                        radius: Theme.radiusSm
                        color: Theme.backgroundSecondary
                        border.color: pathMusicField.activeFocus ? Theme.primary : "transparent"
                    }
                }
                Button {
                    text: "Chọn"
                    font.pixelSize: Theme.fontSizeSm
                    Layout.preferredWidth: 64
                    Layout.preferredHeight: 32
                    background: Rectangle {
                        radius: Theme.radiusSm
                        color: parent.pressed ? Theme.backgroundHover : Theme.backgroundSecondary
                        border.width: 1
                        border.color: Theme.divider
                    }
                    contentItem: Text {
                        text: parent.text
                        font.pixelSize: Theme.fontSizeSm
                        color: Theme.textPrimary
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                    onClicked: {
                        if (!settingsModel) return
                        var p = settingsModel.browseDirectory("music")
                        if (p) pathMusicField.text = p
                    }
                }
                Button {
                    text: "Mặc định"
                    font.pixelSize: Theme.fontSizeSm
                    Layout.preferredWidth: 64
                    Layout.preferredHeight: 32
                    background: Rectangle {
                        radius: Theme.radiusSm
                        color: parent.pressed ? Theme.backgroundHover : Theme.backgroundSecondary
                        border.width: 1
                        border.color: Theme.divider
                    }
                    contentItem: Text {
                        text: parent.text
                        font.pixelSize: Theme.fontSizeSm
                        color: Theme.textPrimary
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                    onClicked: {
                        if (!settingsModel) return
                        settingsModel.clearPathDir("music")
                        pathMusicField.text = ""
                    }
                }
            }

            // Từ khóa đánh thức
            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.spacingSm
                Text {
                    text: "Thư mục từ đánh thức"
                    font.pixelSize: Theme.fontSizeSm
                    color: Theme.textSecondary
                    Layout.preferredWidth: 100
                }
                TextField {
                    id: pathKeywordsField
                    Layout.fillWidth: true
                    text: settingsModel ? settingsModel.pathKeywordsDir : ""
                    onTextEdited: if (settingsModel) settingsModel.pathKeywordsDir = text
                    onEditingFinished: if (settingsModel) settingsModel.pathKeywordsDir = text
                    placeholderText: settingsModel ? settingsModel.pathDefaultKeywordsDir : ""
                    font.pixelSize: Theme.fontSizeSm
                    background: Rectangle {
                        radius: Theme.radiusSm
                        color: Theme.backgroundSecondary
                        border.color: pathKeywordsField.activeFocus ? Theme.primary : "transparent"
                    }
                }
                Button {
                    text: "Chọn"
                    font.pixelSize: Theme.fontSizeSm
                    Layout.preferredWidth: 64
                    Layout.preferredHeight: 32
                    background: Rectangle {
                        radius: Theme.radiusSm
                        color: parent.pressed ? Theme.backgroundHover : Theme.backgroundSecondary
                        border.width: 1
                        border.color: Theme.divider
                    }
                    contentItem: Text {
                        text: parent.text
                        font.pixelSize: Theme.fontSizeSm
                        color: Theme.textPrimary
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                    onClicked: {
                        if (!settingsModel) return
                        var p = settingsModel.browseDirectory("keywords")
                        if (p) pathKeywordsField.text = p
                    }
                }
                Button {
                    text: "Mặc định"
                    font.pixelSize: Theme.fontSizeSm
                    Layout.preferredWidth: 64
                    Layout.preferredHeight: 32
                    background: Rectangle {
                        radius: Theme.radiusSm
                        color: parent.pressed ? Theme.backgroundHover : Theme.backgroundSecondary
                        border.width: 1
                        border.color: Theme.divider
                    }
                    contentItem: Text {
                        text: parent.text
                        font.pixelSize: Theme.fontSizeSm
                        color: Theme.textPrimary
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                    onClicked: {
                        if (!settingsModel) return
                        settingsModel.clearPathDir("keywords")
                        pathKeywordsField.text = ""
                    }
                }
            }

            // MCP Plugins
            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.spacingSm
                Text {
                    text: "Thư mục plugin MCP"
                    font.pixelSize: Theme.fontSizeSm
                    color: Theme.textSecondary
                    Layout.preferredWidth: 100
                }
                TextField {
                    id: pathMcpField
                    Layout.fillWidth: true
                    text: settingsModel ? settingsModel.pathMcpPluginsDir : ""
                    onTextEdited: if (settingsModel) settingsModel.pathMcpPluginsDir = text
                    onEditingFinished: if (settingsModel) settingsModel.pathMcpPluginsDir = text
                    placeholderText: settingsModel ? settingsModel.pathDefaultMcpPluginsDir : ""
                    font.pixelSize: Theme.fontSizeSm
                    background: Rectangle {
                        radius: Theme.radiusSm
                        color: Theme.backgroundSecondary
                        border.color: pathMcpField.activeFocus ? Theme.primary : "transparent"
                    }
                }
                Button {
                    text: "Chọn"
                    font.pixelSize: Theme.fontSizeSm
                    Layout.preferredWidth: 64
                    Layout.preferredHeight: 32
                    background: Rectangle {
                        radius: Theme.radiusSm
                        color: parent.pressed ? Theme.backgroundHover : Theme.backgroundSecondary
                        border.width: 1
                        border.color: Theme.divider
                    }
                    contentItem: Text {
                        text: parent.text
                        font.pixelSize: Theme.fontSizeSm
                        color: Theme.textPrimary
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                    onClicked: {
                        if (!settingsModel) return
                        var p = settingsModel.browseDirectory("mcp")
                        if (p) pathMcpField.text = p
                    }
                }
                Button {
                    text: "Mặc định"
                    font.pixelSize: Theme.fontSizeSm
                    Layout.preferredWidth: 64
                    Layout.preferredHeight: 32
                    background: Rectangle {
                        radius: Theme.radiusSm
                        color: parent.pressed ? Theme.backgroundHover : Theme.backgroundSecondary
                        border.width: 1
                        border.color: Theme.divider
                    }
                    contentItem: Text {
                        text: parent.text
                        font.pixelSize: Theme.fontSizeSm
                        color: Theme.textPrimary
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                    onClicked: {
                        if (!settingsModel) return
                        settingsModel.clearPathDir("mcp")
                        pathMcpField.text = ""
                    }
                }
            }

            Text {
                Layout.fillWidth: true
                text: settingsModel ? settingsModel.pathHints : ""
                font.pixelSize: Theme.fontSizeXs
                color: Theme.textSecondary
                wrapMode: Text.WordWrap
            }
        }

        Item { Layout.fillHeight: true }
    }
}
