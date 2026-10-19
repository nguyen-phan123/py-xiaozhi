# Báo cáo Phân tích Rủi ro Tiềm ẩn py-xiaozhi

**Phạm vi**: `main.py` + `src/` (Orchestration, core, plugins, protocols, audio, mcp, ui glue)  
**Ngày**: 2026-07-19  
**Tính chất**: Rà soát rủi ro chỉ đọc (read-only); không chứa code triển khai fix  
**Đối chiếu**: Pattern hiện có của repository + các điểm tái cấu trúc trong báo cáo; không phụ thuộc Trellis scaffold đã xóa  

---

## 1. Tóm tắt Thực thi (Executive Summary)

> **Trạng thái khắc phục (2026-07-19)**: Các mục Critical / High và P0–P3 đều đã hoàn tất; xem mục §6 và §9. Test hồi quy tại `tests/test_resilience_fixes.py`; thời gian khởi động ~1.7s. Độc lập với Trellis.  
> Quy chuẩn lưu trữ: `.trellis/spec/backend/error-handling.md`, `asyncio-guidelines.md`.  
> Test hồi quy: `tests/test_resilience_fixes.py`.

Kiến trúc dự án theo mô hình 3 tầng (`ServiceContainer` → core services → plugins), với PluginManager / EventBus / TaskManager đảm nhận việc cô lập (isolation).

**Bảng tóm tắt vấn đề gốc (đã khắc phục)**:

| Chủ đề | Trước khi fix | Sau khi fix |
|---|---|---|
| **(a) Khả năng quan sát ngoại lệ (Observability)** | Rất nhiều `except` thiếu `exc_info` | Chuẩn hóa stack trace trên core path; TaskManager dùng `exc_info=exc` |
| **(b) Cô lập module (Module Isolation)** | Dependency fail vẫn chạy rỗng; dirty singleton ở Music/MCP | Gắn cờ failed + tự động skip dependency; container bind/unbind |
| **(c) Lỗi tầng và treo cứng (Cascading/Zombie)** | `create_task` trên từng frame; zombie wait | Audio queue có giới hạn; chốt chặn thoát exit 1 cho critical plugin |

---

## 2. Nuốt ngoại lệ và Khả năng quan sát (Swallowed Exceptions & Observability)

### 2.1 Thống kê Pattern (`src/` + `main.py`)

| Pattern | Số lượng ước tính | Giải thích |
|---|---|---|
| `except Exception` | **275** | Pattern chính của dự án; spec cho phép nhưng chất lượng biên xử lý không đều |
| `except` + logger **không có** `exc_info` | **~182** | Vi phạm spec error-handling: "Critical path bắt buộc phải có stack trace" |
| `except ...: pass` (gồm CancelledError/OSError...) | **~29** | Đa số là dọn dẹp hợp lý; một số ít nuốt lỗi ngầm |
| `except Exception` sau đó `pass` / `return` ngầm / `continue` | **~15** | Thực sự "nuốt lỗi và gần như không để lại dấu vết" |
| `except:` trần (bare except) | **0** | Đạt chuẩn, không vi phạm |
| `asyncio.create_task` (gồm tự quản lý hợp lệ) | **~20** | Nhiều chỗ không đi qua TaskManager (xem §4) |

Từ khóa tìm kiếm: `except Exception`, `except ...: pass`, `exc_info`, `asyncio.create_task`, `threading.Thread`, `get_instance`.

### 2.2 Critical / High: Mất khả năng quan sát (Observability Failure)

#### H-1 EventBus nuốt exception của handler và không có stack trace  
- **Vị trí**: `src/core/event_bus.py` `_safe_call` ~L166–178  
- **Hiện tượng**: Bất kỳ subscriber nào ném lỗi → Chỉ ghi 1 dòng log `处理器 X 执行异常: {e}`, **không có traceback**; `emit` dùng `gather(..., return_exceptions=True)` gộp lại khiến caller hoàn toàn không phát hiện lỗi.  
- **Nguyên nhân gốc rễ (Root Cause)**: Thiết kế cô lập đúng, nhưng log vi phạm spec Pattern #1 (ranh giới xử lý phải có `exc_info=True`).  
- **Bán kính ảnh hưởng (Blast Radius)**: Toàn bộ luồng đi qua EventBus gồm UI, State Machine, Protocol, Music; khi debug chỉ thấy "trạng thái không cập nhật", không biết bên nào gãy.  
- **Hướng giảm thiểu**: Sửa `_safe_call` thành `logger.error(..., exc_info=True)`; có thể cân nhắc thêm failure counter/metrics cho event trọng yếu (như `DEVICE_STATE_CHANGED`).

#### H-2 PluginManager thất bại vòng đời không có stack trace  
- **Vị trí**: `src/plugins/manager.py` `setup_all` / `start_all` / `notify_*` ~L150–203  
- **Hiện tượng**: `logger.error(f"插件 {name} setup 失败: {e}")` thiếu `exc_info`; plugin lỗi vẫn nằm trong danh sách, các hook `start` / `notify` tiếp tục gọi vào nó.  
- **Root Cause**: Ranh giới cô lập bắt được exception nhưng không đánh dấu plugin là failed, cũng không lưu lại stack trace.  
- **Blast Radius**: Plugin khởi tạo dở dang tiếp tục lỗi ở hook sau hoặc phát sinh NPE dạng AttributeError; log bị spam, khó trace root cause.  
- **Hướng giảm thiểu**: Setup thất bại thì đánh dấu `_failed=True` và loại khỏi danh sách notify; chuẩn hóa log với `exc_info=True`; tự động skip start đối với plugin hạ tầng có `requires` trỏ tới plugin đã failed.

#### H-3 TaskManager log lỗi task có thể mất traceback  
- **Vị trí**: `src/core/task_manager.py` `_on_done` ~L94–99  
```python
exc = t.exception()
if exc:
    logger.error(f"任务 {name} 异常结束: {exc}", exc_info=True)
```  
- **Hiện tượng**: Trong done callback không có active exception context, `exc_info=True` **thường sẽ không** đính kèm traceback của `exc` (cần dùng `exc_info=(type(exc), exc, exc.__traceback__)` hoặc `logger.error(..., exc_info=exc)`).  
- **Blast Radius**: Tất cả business task chạy qua `spawn` (UI start, command scheduling...) có log "kết thúc bất thường" bị thiếu thông tin.  
- **Hướng giảm thiểu**: Dùng `exc_info=exc` (Python 3.5+) hoặc truyền tuple 3 phần tử tường minh.

#### H-4 Hot path JSON của Protocol / Container nuốt lỗi thiếu stack trace  
- **Vị trí**:  
  - `src/bootstrap/container.py` `_on_incoming_json` ~L362–377: `logger.error(f"处理 JSON 消息失败: {e}")`  
  - `src/core/protocol_manager.py` `connect` ~L124–126: Exception kết nối không có stack trace  
  - `src/core/resource_pool.py` ~L54–55: Dọn dẹp thất bại không có stack trace  
- **Hiện tượng**: Khi xử lý TTS / State Machine thất bại chỉ còn lại string thông báo lỗi.  
- **Blast Radius**: Lỗi sai lệch trạng thái voice session rất khó tái hiện.  
- **Hướng giảm thiểu**: Đồng bộ hóa ranh giới xử lý với `exc_info=True`.

### 2.3 Medium: Nuốt lỗi ngầm (Silent Swallow)

#### M-1 Dọn dẹp Audio có 2 tầng except, tầng ngoài dùng `pass`  
- **Vị trí**: `src/plugins/audio.py` `register_resources` ~L140–154  
- **Hiện tượng**: Khi import music player thất bại, tầng ngoài rơi vào `except Exception: pass`, **hoàn toàn không có log**.  
- **Blast Radius**: Giai đoạn shutdown có thể bị rò rỉ (leak) music/decoder; rất khó phát hiện từ log.  
- **Hướng giảm thiểu**: Tối thiểu ghi `logger.debug(..., exc_info=True)` theo spec "nếu phân vân thì dùng #2 warning".

#### M-2 `_should_send_microphone_audio` trả về False trong im lặng  
- **Vị trí**: `src/plugins/audio.py` ~L188–193  
```python
except Exception:
    return False
```  
- **Hiện tượng**: Khi query trạng thái bị lỗi, hệ thống ngừng gửi audio uplink mà không ghi log.  
- **Blast Radius**: User gặp tình trạng "đột nhiên bot không nghe thấy tôi nói", khó liên kết tới bug của state machine.  
- **Hướng giảm thiểu**: Ghi warning 1 lần + return False.

#### M-3 Các nhánh return ngầm / fallback khác (chấp nhận được nhưng cần lưu ý)  
| Vị trí | Hành vi | Đánh giá |
|---|---|---|
| `main.py` L163–164 SIGTRAP | `pass` | Chấp nhận được (đăng ký signal) |
| `src/constants/constants.py` L75–77 | frame duration default 20 | Chấp nhận được |
| `src/activation/service.py` L466–467 | efuse đọc lỗi → chưa kích hoạt | Chấp nhận được, khuyến nghị log debug |
| `src/protocols/websocket_protocol.py` L304–305 | `is_audio_channel_opened` lỗi → False | Chấp nhận được |
| `src/plugins/manager.py` L54–55 | `get_plugin` lỗi → None | Phòng thủ quá mức, dict.get hầu như không throw |
| MCP app launcher/scanner nhiều chỗ | Probe thất bại continue/return | Phía tools chấp nhận được |

### 2.4 Mức độ tuân thủ Quy chuẩn (error-handling.md)

| Tiêu chuẩn | Hiện trạng |
|---|---|
| Cấm dùng `except:` trần | ✅ Không phát hiện |
| Critical path phải có `exc_info=True` | ❌ Vi phạm nhiều (EventBus, PluginManager, Protocol, UI bridge) |
| Cấm dùng `logger.exception` | ✅ Không phát hiện sử dụng |
| Plugin lỗi do manager cô lập, trong plugin không nuốt lỗi | ⚠️ Manager đã cô lập, nhưng bên trong audio/mcp vẫn còn try lồng (một phần hợp lý) |
| Nuốt lỗi ngầm chỉ dùng ở path thực sự vô nghĩa | ⚠️ Một số path dọn dẹp bắt lỗi quá rộng |

---

## 3. Tính Toàn vẹn của Module hóa và Cô lập (Modularity & Isolation)

### 3.1 Ý đồ Kiến trúc vs Thực tế

Tài liệu (`architecture-principles.md`) yêu cầu:
- Plugin chỉ truy cập core thông qua `PluginContext` / `PluginCommands`  
- Core không import implementation cụ thể của plugins / ui / protocols  
- MCP tools cố gắng không tạo side-effect, không import core (ngoại trừ `music_player`)

**Đánh giá thực tế**:

| Mục kiểm tra | Kết quả |
|---|---|
| `src/core/*` import plugins/ui | ✅ Không phát hiện (cô lập tốt) |
| Plugins truy cập container qua interface Protocol | ✅ Đã có pattern Adapter |
| MCP tools import core | ⚠️ `music_player.py` import trực tiếp `from src.core.event_bus import Events` |
| Quản lý dependency topology plugin + inject | ✅ Dùng `requires` + Kahn topology |
| Plugin lỗi chặn các plugin phụ thuộc | ❌ **Chưa triển khai** (xem H-5) |

### 3.2 High: Lỗ hổng Cô lập (Isolation Holes)

#### H-5 Dependency plugin thất bại nhưng downstream vẫn khởi động (Hệ thống "chết lâm sàng")  
- **Vị trí**:  
  - `AudioPlugin.setup` ~L52–54: Thất bại nhưng gán `self.codec = None` rồi chạy tiếp  
  - `WakeWordPlugin.requires = ["audio"]`, hàm `start` thấy không có codec chỉ warning rồi return (`wake_word.py` ~L57–59)  
  - `PluginManager.setup_all` không dựa vào kết quả setup để loại bỏ hoặc lan truyền trạng thái fail  
- **Hiện tượng**: Khởi tạo Microphone / PortAudio thất bại → Tiến trình vẫn vào `wait_shutdown`, UI hiển thị bình thường nhưng tính năng wake-word/hội thoại tê liệt hoàn toàn; người dùng tưởng app vẫn hoạt động.  
- **Blast Radius**: Audio là plugin nền tảng priority=10; lỗi audio cần được coi là **degraded mode** hoặc **fatal error**, hiện tại chưa phân định rõ.  
- **Hướng giảm thiểu**:  
  - Định nghĩa trạng thái `health` của plugin: healthy / degraded / failed;  
  - Dependency trong `requires` failed → Downstream auto-skip;  
  - Tùy chọn: Critical plugin (audio/ui) fail thì gọi `request_shutdown` hoặc hiện banner báo degraded rõ ràng.

#### H-6 Global Singleton xuyên suốt lifecycle khiến container không thể teardown / recreate sạch  
- **Vị trí**:  
  - `ConfigManager` — `src/utils/config_manager.py`, dùng ở module level  
  - `constants.py` L6: `config = ConfigManager.get_instance()` **tạo side effect ngay khi import**  
  - `McpServer.get_instance()` — `src/mcp/mcp_server.py`  
  - `get_music_player_instance()` — `src/mcp/tools/music/music_player.py` L1288–1297  
  - `ActivationService` / `LoggingConfigManager` dùng cùng pattern  
- **Hiện tượng**: `ServiceContainer.shutdown` đã giải phóng resource pool, nhưng state của singleton (danh sách tools, con trỏ music codec, injected event_bus) vẫn tồn lưu; gây bẩn state khi test hoặc hot reload.  
- **Blast Radius**: Ranh giới module trên tài liệu là plugin, nhưng runtime thực chất là **process-level shared heap**.  
- **Hướng giảm thiểu**: Chuyển singleton về container quản lý và inject; tối thiểu phải cung cấp `reset_for_tests()`; loại bỏ việc đọc config khi import `constants`.

#### H-7 Ghép nối 2 chiều giữa Audio ↔ Music, vượt qua ranh giới plugin  
- **Vị trí**:  
  - `AudioPlugin.setup` gọi `get_music_player_instance().set_audio_codec`  
  - `McpPlugin.setup` lại inject EventBus vào cùng MusicPlayer đó  
  - Cleanup path cả hai bên đều gọi stop music (`audio.py` resource cleanup + `mcp.py` resource cleanup)  
- **Hiện tượng**: Thứ tự shutdown phụ thuộc vào thứ tự đăng ký trong resource_pool; một bên fail thì bên kia vẫn giữ codec đã close → Exception thứ cấp bị nuốt lỗi.  
- **Blast Radius**: Treo khi tắt máy, thỉnh thoảng lỗi playback "codec is None".  
- **Hướng giảm thiểu**: Music quy về một plugin sở hữu duy nhất; phía còn lại chỉ phát event (`MUSIC_*`), không can thiệp trực tiếp set codec.

#### M-4 EventBus dùng string event name không có type constraint  
- **Vị trí**: `src/core/event_bus.py` Hằng số `Events` + `emit(event: str, data: Any)`  
- **Hiện tượng**: Typo tên event sẽ trôi qua trong im lặng vì không có subscriber; data payload chỉ dựa vào quy ước.  
- **Blast Radius**: Dễ phát sinh bug "bắn event nhưng không ai nhận" khi refactor chéo module.  
- **Hướng giảm thiểu**: Giữ gọn nhẹ; có thể thêm assertion `has_handlers` ở chế độ debug hoặc typed payload dataclass (một số UI/music đã dùng).

#### M-5 UIPlugin liên kết trực tiếp vào implementation nội bộ của ViewManager  
- **Vị trí**: `src/plugins/ui.py` nhiều chỗ gọi `self.view_manager.main_model.set_*`, `_emotion_service`  
- **Hiện tượng**: Phân nhánh if/else cho GUI/CLI phình to; View đổi tên nội bộ sẽ làm gãy plugin.  
- **Blast Radius**: Chi phí refactor UI cao, không phải nguyên nhân chính gây crash runtime.  
- **Hướng giảm thiểu**: Đồng bộ qua UI Facade (hiện đã có một phần như set_status/set_tts_text).

### 3.3 Những điểm làm tốt về mặt cô lập

- **PluginManager chủ động cô lập** setup/start/notify/stop: Exception của từng plugin mặc định không ngắt vòng lặp — **đúng thiết kế**.  
- **EventBus `_safe_call`**: Một handler fail không hủy các handler khác — **đúng thiết kế** (thiếu stack trace là vấn đề riêng).  
- **ResourcePool giải phóng ngược thứ tự + một resource fail vẫn tiếp tục** — Phù hợp với cơ chế partial shutdown khi tắt ứng dụng.  
- **Protocol audio stream trực tiếp** (`set_audio_handler`) tránh backpressure cho EventBus — Tối ưu hóa kiến trúc có chủ đích.  
- **main.py top-level** bắt `Exception` và kèm `exc_info=True` — Exception chưa bắt ở cấp tiến trình có điểm lưu vết.

---

## 4. Lỗi Đơn module → Crash Toàn cục / Treo cứng (Single Failure → Cascade/Zombie)

### 4.1 Critical / High

#### C-1 Protocol layer gọi fire-and-forget `create_task` (Anti-pattern theo quy chuẩn)  
- **Vị trí**: `src/core/protocol_manager.py` L68–78  
```python
def _on_incoming_json(...):
    asyncio.create_task(self._event_bus.emit(Events.INCOMING_JSON, json_data))

def _on_incoming_audio(...):
    asyncio.create_task(self._incoming_audio_handler(data))  # Mỗi audio frame
```  
- **Hiện tượng** (đã được cảnh báo trong `asyncio-guidelines.md`):  
  1. Task không nằm trong `TaskManager` → **Shutdown không cancel được**, gây lỗi "Event loop stopped before Future completed" hoặc treo I/O;  
  2. Không có done_callback → Exception có thể biến thành "Task exception was never retrieved";  
  3. **Mỗi frame audio** đều `create_task`: Nếu handler xử lý chậm, hàng đợi task bùng nổ → Tràn RAM, delay scheduling, cuối cùng làm event loop nghẽn cứng (**tiến trình không crash nhưng toàn bộ app không phản hồi**).  
- **Blast Radius**: Tê liệt toàn bộ luồng Audio/JSON; UI và plugins cùng process bị bỏ đói tài nguyên (starvation).  
- **Hướng giảm thiểu**:  
  - JSON: Dùng `TaskManager.spawn` hoặc gom vào serial queue sẵn có;  
  - Audio: Ưu tiên dùng bounded queue + single consumer task khi callback đồng bộ không thể await trực tiếp; tuyệt đối không tạo task trên từng packet.

#### H-8 MQTT Callback Thread → Gọi `create_task` trần  
- **Vị trí**: `src/protocols/mqtt_protocol.py` ~L237–240, L257–260, L570...  
```python
self.loop.call_soon_threadsafe(
    lambda: asyncio.create_task(self._attempt_reconnect(...))
)
```  
- **Hiện tượng**: Task không được theo dõi tương tự C-1; ngoài ra, late binding của `lambda` closure với biến `rc`/`error_msg` có thể lấy sai giá trị khi disconnect liên tục; gọi `create_task` trong thread nếu loop đã đóng sẽ ném exception ngoài tầm kiểm soát.  
- **Blast Radius**: Bão reconnect, mất callback báo lỗi mạng → State machine bị kẹt ở LISTENING/SPEAKING.  
- **Hướng giảm thiểu**: `asyncio.run_coroutine_threadsafe` + giữ lại Future; hoặc `call_soon_threadsafe` gọi `TaskManager.schedule_nowait`; bind closure bằng default argument.

#### H-9 Ứng dụng "chạy rỗng" sau khi Critical Plugin thất bại  
- **Vị trí**: `ServiceContainer.run` ~L232–242: Sau khi plugins setup/start không kiểm tra health, gọi thẳng `await self.tasks.wait_shutdown()`  
- **Hiện tượng**: UI setup fail (bị manager nuốt) → Không cửa sổ, không CLI, nhưng vẫn block ở wait_shutdown, chỉ có thể kill bằng OS signal. Lỗi Audio cũng tương tự.  
- **Blast Radius**: **Zombie application (treo cứng toàn cục)**, không sinh ra traceback crash.  
- **Hướng giảm thiểu**: Thêm health check sau setup; critical plugin fail thì exit code 1 hoặc in thông báo "degraded" trên CLI.

#### H-10 Xử lý Network Error quá mỏng  
- **Vị trí**: `container.py` `_on_network_error` ~L351–352  
```python
async def _on_network_error(...):
    self.state.set_keep_listening(False)
```  
- **Hiện tượng**: Không chuyển device_state, không abort, không đảm bảo luồng phục hồi ngoài UI hoàn chỉnh. Trạng thái vẫn có thể treo ở SPEAKING/LISTENING.  
- **Blast Radius**: Rớt mạng khiến hành vi phím bấm/wake-word sai lệch cho tới khi user bấm abort thủ công.  
- **Hướng giảm thiểu**: Khi mất mạng, đồng bộ gọi `set_device_state(IDLE)` + hủy keep_listening + hiển thị cảnh báo.

### 4.2 Medium: Crash Thực tế và Biên Xử lý

#### M-6 Các lỗi Top-level đỡ được vs Không thể đỡ  
- **Đỡ được**: `main.py` L228–233 với `except Exception`; `ServiceContainer.run` L245–247.  
- **Không thể đỡ (cấp tiến trình)**:  
  - **Segfault từ C extension** trong audio callback thread (PortAudio / Opus / webrtc_apm / sherpa-onnx);  
  - Lỗi chưa bắt trong `threading.Thread` không thuộc main thread;  
  - Native assertion từ Qt / qasync.  
- **Ví dụ**: `audio_codec.py` `_input_callback` / `_output_callback` có Python try, nhưng native error từ numpy/opus có thể abort trực tiếp tiến trình.  
- **Hướng giảm thiểu**: Giữ callback mỏng nhất có thể; fail-fast khi khởi tạo native library; ghi nhận qua OS system log khi crash.

#### M-7 UI Event Handler chưa tự bọc try/except  
- **Vị trí**: `src/plugins/ui.py` `_press` / `_send_text` / `_abort`...  
- **Hiện tượng**: Exception phụ thuộc vào fallback `_safe_call` của EventBus (xem H-1); nếu sau này gọi trực tiếp bằng `await` sẽ bị văng lỗi.  
- **Blast Radius**: Hiện tại được EventBus che chắn nên không crash toàn cục; nhưng kết hợp với H-1 sẽ gây hiện tượng "bấm nút không phản hồi mà không có log stack trace".

#### M-8 Side effect khi import `constants.py`  
- **Vị trí**: L6 `config = ConfigManager.get_instance()`  
- **Hiện tượng**: Bất kỳ file nào import constants đều kích hoạt khởi tạo thư mục config/đọc đĩa; test hoặc tool script vô tình kích hoạt I/O; config hỏng khiến toàn bộ chuỗi import gãy → **Khởi động thất bại sớm**.  
- **Hướng giảm thiểu**: Lazy load lấy config bên trong `get_frame_duration` (đã có code sẵn, cần xóa dòng ở module level).

#### M-9 Dọn dẹp tài nguyên thất bại không có stack trace + chạy tiếp  
- **Vị trí**: `resource_pool.py` L49–55  
- **Hiện tượng**: Một cleanup ném lỗi bị nuốt (thiếu stack trace), tài nguyên sau vẫn giải phóng — partial shutdown hợp lý, nhưng khó trace leak tài nguyên.  
- **Hướng giảm thiểu**: Bổ sung `exc_info=True`.

### 4.3 Các path không làm chết tiến trình khi module A lỗi

- Plugin setup/start/notify (được PluginManager bọc)  
- EventBus handler (`_safe_call`)  
- Task chạy qua `TaskManager.spawn` (done callback ghi log, không re-raise ra unhandled exception handler của loop)  
- MCP tool call (`mcp_server._handle_tool_call` bắt lỗi và trả lời `_reply_error`)

---

## 5. Bảng Tổng hợp Mức độ Nghiêm trọng

| ID | Mức độ | Chủ đề | Tóm tắt | Vị trí |
|---|---|---|---|---|
| C-1 | **Critical** | Cascade/Zombie | Protocol JSON/Audio `create_task` trên từng message gây nghẽn event loop | `protocol_manager.py:68-78` |
| H-1 | **High** | Nuốt Exception | EventBus nuốt exception và mất stack trace | `event_bus.py:166-178` |
| H-2 | **High** | Nuốt Exception + Cô lập | Plugin lỗi không có stack trace, không đánh dấu failed | `manager.py:150-203` |
| H-3 | **High** | Nuốt Exception | Task exception dùng `exc_info=True` có thể mất traceback | `task_manager.py:94-99` |
| H-4 | **High** | Nuốt Exception | Hot path của Container / Protocol thiếu stack trace | `container.py:362-377`... |
| H-5 | **High** | Cô lập | Audio fail nhưng app vẫn chạy rỗng | `audio.py:52-54` + container run |
| H-6 | **High** | Cô lập | Global singleton phá vỡ container lifecycle | config/mcp/music get_instance |
| H-7 | **High** | Cô lập | Audio ↔ Music ghép nối 2 chiều | `audio.py` + `mcp.py` + music_player |
| H-8 | **High** | Cascade | MQTT thread gọi `create_task` trần / late binding closure | `mqtt_protocol.py:237+` |
| H-9 | **High** | Cascade | Critical plugin lỗi dẫn tới zombie wait_shutdown | `container.py:232-242` |
| H-10 | **High** | Cascade | Lỗi mạng không reset trạng thái thiết bị | `container.py:351-352` |
| M-1..M-9 | **Medium** | Hỗn hợp | Silent pass, UI coupling, bề mặt C crash... | Xem chi tiết ở trên |
| — | Low | — | CancelledError pass, QueueEmpty pass, SIGTRAP pass... | Nhiều nơi, chấp nhận được |

---

## 6. Thứ tự Ưu tiên Khuyến nghị

### P0 (Thực hiện ngay)
1. **Triệt tiêu fire-and-forget trên hot path**: Audio trong `protocol_manager` đổi sang bounded queue; JSON đi qua `TaskManager.spawn`.  
2. **Chuẩn hóa `exc_info` trên critical path**: EventBus, PluginManager, ResourcePool, container JSON handler, TaskManager done callback.  
3. **Chốt chặn kiểm tra sức khỏe critical plugin**: audio/ui setup fail → Thoát với exit code hoặc báo degraded rõ ràng, cấm silent zombie.

### P1
4. Gắn cờ `_failed` cho plugin + tự động skip dependency.  
5. Đưa toàn bộ task đa luồng từ MQTT/GPIO/CLI vào TaskManager hoặc `run_coroutine_threadsafe` để theo dõi Future.  
6. Chuẩn hóa việc kéo trạng thái về IDLE khi gặp lỗi mạng.

### P2 (Đã hoàn tất)
7. Cơ chế bind/unbind MusicPlayer/McpServer vào container + inject qua plugin.  
8. Lazy load ConfigManager trong `constants.py`.  
9. Thu gọn giao tiếp UI qua Facade.  
10. Theo dõi lịch điều phối event từ CLI/GPIO.

### P3 / Hoàn thiện (Đã hoàn tất)
11. Inject container `TaskManager` vào CLI/GPIO/GUI; `_safe_emit` ưu tiên dùng `schedule_nowait`.  
12. Bổ sung `exc_info` cho `logger.error` trên hot path WebSocket/MQTT.  
13. Hook `ConfigManager.reset_instance()` phục vụ test.  
14. Tối ưu khởi động: Trì hoãn scan Settings/OpenCV; lazy load SettingsModel.  
15. Quản lý việc hủy task lời bài hát; GUIActivation dùng `get_running_loop` + `create_task`.

### Chủ ý Giữ lại / Không thể loại bỏ hoàn toàn bằng code
- **ConfigManager process singleton**: Nguồn cấu hình chuẩn toàn cục; chỉ cấp hàm reset cho unit test.  
- **Segfault từ native C extension** (PortAudio/Opus/ONNX): Ranh giới Python không thể can thiệp.  
- **MCP tools lấy MusicPlayer qua get_instance**: Đường dẫn tương thích ngược, runtime đã bind vào container instance.

---

## 9. Bảng Đối chiếu Khắc phục (C/H)

| ID | Trạng thái | Điểm then chốt trong triển khai |
|---|---|---|
| C-1 | ✅ | Audio bounded queue + JSON dùng TaskManager.spawn |
| H-1 | ✅ | EventBus thêm `exc_info=True` |
| H-2 | ✅ | mark_failed + skip dependency + stack trace |
| H-3 | ✅ | Sửa thành `exc_info=exc` |
| H-4 | ✅ | Stack trace cho container/resource_pool/protocol |
| H-5 | ✅ | Audio mark_failed + chốt chặn khởi động |
| H-6 | ✅ | Music/MCP bind; Config giữ singleton + reset hook |
| H-7 | ✅ | Dependency injection + vòng đời detach |
| H-8 | ✅ | MQTT dùng `_schedule_coro` |
| H-9 | ✅ | Health check cho critical plugin, fail thì exit 1 |
| H-10 | ✅ | Lỗi mạng → chuyển trạng thái về IDLE |

---

## 7. Đối chiếu Ba Chủ đề Lớn (Hậu Kiểm tra)

### (a) Ngoại lệ bị nuốt, không ném ra được / Không thể chẩn đoán
- **Đã fix**: Đồng bộ `exc_info` trên các core path (EventBus / PluginManager / TaskManager / ResourcePool / Protocol hot path); bổ sung log cho path âm thầm trong audio.  
- **Không tồn tại**: Bare `except:` trần (toàn repo = 0).  
- **Còn sót lại**: Các module ngoại vi (settings / activation / một số MCP tools) vẫn còn `logger.error(f"...{e}")` không có stack trace, thuộc về nợ kỹ thuật khả năng quan sát (observability debt), không phải lỗ hổng kiến trúc.  
- **Nuốt lỗi có chủ ý**: Việc cô lập plugin/event vẫn là hành vi thiết kế có chủ đích; hiện đã có mark_failed + stack trace đi kèm.

### (b) Module hóa không thể cô lập hoàn toàn
- **Đã cải thiện**: Plugin failed + skip dependency; Music/MCP bind/unbind với container; UI facade; inject TaskManager vào UI.  
- **Vẫn giữ lại (hợp lý)**: ConfigManager process singleton; MCP tools truy cập qua `get_*_instance` (runtime trỏ tới container instance).  
- **EventBus**: Vẫn dùng string event name + Any data (ưu tiên thấp).

### (c) Ngoại lệ tại module A kéo sập toàn cục
- **Đã fix**: Audio bounded queue ở protocol; chốt chặn exit 1 cho critical plugin; mạng lỗi đưa về IDLE; MQTT dispatch có thể theo dõi.  
- **Trải nghiệm khởi động**: Trì hoãn scan Settings/OpenCV, giảm cold start từ ~55s xuống ~2s.  
- **Vẫn có thể xảy ra**: Segfault từ native C extension; task lời bài hát/phát nhạc nay đã có thể cancel có kiểm soát.  
- **Kết luận**: Các kịch bản cấp kiến trúc kiểu "process còn sống nhưng tính năng đã chết" đã được đóng lại; phần còn lại là tinh chỉnh kỹ thuật (polish).

---

## 8. Phụ lục: Bằng chứng Điều tra & Lấy mẫu (Snapshot Trước khi Fix)

### 8.1 Thống kê Lệnh / Pattern (Quét lần đầu 2026-07-19)
```
except Exception            → ~275
except + logger không có exc_info → ~182
except ...: pass            → ~29
asyncio.create_task         → ~20 (gồm tự quản lý hợp lệ)
get_instance(               → ~32 điểm gọi
threading.Thread            → ~7
```

### 8.2 Bảng Đối chiếu Mẫu Code (Đợt soát đầu)

| File | Dòng | Pattern |
|---|---|---|
| `src/core/event_bus.py` | 172–178 | Đã fix: exc_info |
| `src/core/task_manager.py` | 94–99 | Đã fix: exc_info=exc |
| `src/plugins/manager.py` | 150–162 | Đã fix: failed + stack trace |
| `src/core/protocol_manager.py` | 68–78 | create_task không kiểm soát |
| `src/plugins/audio.py` | 52–54, 153–154 | soft fail + pass |
| `src/bootstrap/container.py` | 245–249, 351–352, 362–377 | run fallback; xử lý network/JSON |
| `src/protocols/mqtt_protocol.py` | 237–240 | thread + create_task |
| `src/constants/constants.py` | 6 | import-time singleton |
| `src/core/resource_pool.py` | 49–55 | cleanup catch không có stack |
| `main.py` | 163–164, 231–233 | pass có chủ đích + top-level fallback |

### 8.3 Ghi chú
- Dự án đã gỡ bỏ Trellis scaffold; báo cáo này cùng với `deep-audit.md` là tài liệu kiểm toán và khắc phục độc lập, không gắn với `.trellis/`.

---

*Báo cáo dựa trên phân tích mã tĩnh + nhật ký khắc phục. Hành vi động căn cứ theo log thực tế và `tests/test_resilience_fixes.py`.*
