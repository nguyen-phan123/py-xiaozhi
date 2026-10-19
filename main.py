import argparse
import asyncio
import locale
import os
import signal
import sys

# Windows: Ép C/C++ runtime dùng UTF-8, khắc phục lỗi font khi sherpa-onnx đọc file pinyin thanh điệu
if sys.platform == "win32":
    os.environ["PYTHONIOENCODING"] = "utf-8"
    try:
        locale.setlocale(locale.LC_ALL, ".UTF-8")
    except locale.Error:
        pass

os.environ["QSG_RHI_BACKEND"] = "opengl"
# Bắt buộc qasync sử dụng PySide6
os.environ["QT_API"] = "pyside6"
# Dùng style Basic để hỗ trợ custom controls
os.environ["QT_QUICK_CONTROLS_STYLE"] = "Basic"


def parse_args():
    """Phân tích các tham số dòng lệnh."""
    from src.constants.system import SystemConstants

    parser = argparse.ArgumentParser(description=SystemConstants.APP_DISPLAY_NAME)
    # Lựa chọn chế độ chạy
    # - gui: Chế độ giao diện đồ họa, sử dụng PySide6 + QML
    # - cli: Chế độ dòng lệnh, tương tác qua terminal (nhẹ, phù hợp cho máy không màn hình/SSH)
    # - tui: TUI toàn màn hình (Textual), có thể chỉnh sửa cấu hình; cần uv sync --extra tui
    # - gpio: Chế độ nút bấm GPIO, chỉ hỗ trợ Linux (Raspberry Pi), điều khiển qua nút bấm vật lý
    parser.add_argument(
        "--mode",
        choices=["gui", "cli", "tui", "gpio"],
        default="gui",
        help="Chế độ chạy (mặc định gui): gui / cli / tui(terminal toàn màn hình) / gpio(chỉ Linux)",
    )
    parser.add_argument(
        "--protocol",
        choices=["mqtt", "websocket"],
        default="websocket",
        metavar="PROTOCOL",
        help="Giao thức truyền thông: mqtt hoặc websocket (mặc định websocket; cần viết --protocol mqtt)",
    )
    parser.add_argument(
        "--skip-activation",
        action="store_true",
        help="Bỏ qua quy trình kích hoạt, khởi chạy trực tiếp ứng dụng (chỉ dùng cho debug)",
    )
    return parser.parse_args()


# Phân tích tham số trước, sau đó mới khởi tạo cấu hình và log (ngăn ConfigManager lazy singleton)
_args = parse_args()

from src.utils.config_manager import initialize_config  # noqa: E402

initialize_config()

from src.logging import load_logging_config, setup_logging  # noqa: E402

# Chế độ CLI/TUI vô hiệu hóa xuất log ra console (giao diện sẽ tiếp quản)
setup_logging(
    enable_console=(_args.mode not in ("cli", "tui")),
    config=load_logging_config(),
)

from src.bootstrap.container import ServiceContainer  # noqa: E402
from src.constants.system import SystemConstants  # noqa: E402
from src.logging import get_logger  # noqa: E402

logger = get_logger()


async def handle_activation(mode: str) -> bool:
    """Xử lý quy trình kích hoạt thiết bị.

    Args:
        mode: Chế độ chạy, "gui", "cli", "tui" hoặc "gpio"

    Returns:
        bool: Kích hoạt có thành công hay không
    """
    try:
        from src.activation import ActivationService, create_activation_ui

        logger.info("Bắt đầu kiểm tra quy trình kích hoạt thiết bị...")
        activation_service = await ActivationService.create()
        init_result = await activation_service.initialize()

        if not init_result.get("success", False):
            logger.error(
                f"Khởi tạo thất bại: {init_result.get('error', 'Lỗi không xác định')}"
            )
            return False

        if not init_result.get("need_activation_ui", False):
            logger.info("Thiết bị đã được kích hoạt, bỏ qua quy trình kích hoạt")
            return True

        ui = create_activation_ui(mode, activation_service, init_result)
        return await ui.run()

    except Exception as e:
        logger.error(f"Quy trình kích hoạt xảy ra ngoại lệ: {e}", exc_info=True)
        return False


async def start_app(mode: str, protocol: str, skip_activation: bool) -> int:
    """Điểm vào thống nhất để khởi chạy ứng dụng."""
    global _container  # Dùng cho xử lý SIGINT
    logger.info(f"Starting {SystemConstants.APP_DISPLAY_NAME}")

    # Xử lý quy trình kích hoạt
    if not skip_activation:
        activation_success = await handle_activation(mode)
        if not activation_success:
            logger.error("Kích hoạt thiết bị thất bại, chương trình đang thoát")
            return 1
    else:
        logger.warning("Bỏ qua quy trình kích hoạt (chế độ debug)")

    # Tạo và khởi chạy ứng dụng
    _container = ServiceContainer()
    return await _container.run(mode=mode, protocol=protocol)


# Tham chiếu container toàn cục, dùng cho xử lý SIGINT
_container = None


if __name__ == "__main__":
    exit_code = 1
    try:
        # Sử dụng các tham số đã phân tích
        args = _args

        # Phát hiện môi trường Wayland và thiết lập cấu hình Qt platform plugin
        import os

        is_wayland = (
            os.environ.get("WAYLAND_DISPLAY")
            or os.environ.get("XDG_SESSION_TYPE") == "wayland"
        )

        if args.mode == "gui" and is_wayland:
            if "QT_QPA_PLATFORM" not in os.environ:
                os.environ["QT_QPA_PLATFORM"] = "wayland;xcb"
                logger.info("Môi trường Wayland: Thiết lập QT_QPA_PLATFORM=wayland;xcb")
            os.environ.setdefault("QT_WAYLAND_DISABLE_WINDOWDECORATION", "1")
            logger.info("Đã phát hiện môi trường Wayland, áp dụng cấu hình tương thích")

        # Xử lý tín hiệu (signals)
        try:
            if hasattr(signal, "SIGTRAP"):
                signal.signal(signal.SIGTRAP, signal.SIG_IGN)
        except Exception:
            pass

        if args.mode == "gui":
            # Chế độ GUI: Sử dụng PySide6 + qasync
            try:
                import qasync
                from PySide6.QtWidgets import QApplication
            except ImportError as e:
                logger.error(
                    "GUI Mode yêu cầu PySide6 + qasync, môi trường hiện tại chưa cài đặt.\n"
                    "please install dependency GUI trong venv của dự án rồi thử lại:\n"
                    "  uv sync --extra gui\n"
                    "  # hoặc: pip install '.[gui]'\n"
                    "Sau đó:\n"
                    "  uv run python main.py\n"
                    "  # hoặc: .venv/bin/python main.py\n"
                    "Nếu không dùng GUI:\n"
                    "  python main.py --mode cli\n"
                    "  python main.py --mode tui   # cần uv sync --extra tui\n"
                    f"(Lỗi gốc: {e})"
                )
                sys.exit(1)

            qt_app = QApplication.instance() or QApplication(sys.argv)
            qt_app.setQuitOnLastWindowClosed(False)

            loop = qasync.QEventLoop(qt_app)
            asyncio.set_event_loop(loop)
            logger.info("Installed Event loop PySide6 + qasync")

            # Thiết lập xử lý tín hiệu SIGINT - yêu cầu đóng thông qua TaskManager
            shutdown_state = {"requested": False}

            def handle_sigint(*_):
                if shutdown_state["requested"]:
                    return
                shutdown_state["requested"] = True
                logger.info("Nhận được tín hiệu SIGINT, đang thoát...")

                # Yêu cầu shutdown mềm mại thông qua TaskManager
                try:
                    if _container and _container.tasks:
                        _container.tasks.request_shutdown()
                    else:
                        # Container chưa sẵn sàng, thoát trực tiếp Qt
                        if loop.is_running():
                            loop.call_soon_threadsafe(qt_app.quit)
                except Exception:
                    qt_app.quit()

            signal.signal(signal.SIGINT, handle_sigint)

            try:
                with loop:
                    exit_code = loop.run_until_complete(
                        start_app(args.mode, args.protocol, args.skip_activation)
                    )
            except RuntimeError as e:
                # Bắt lỗi "Event loop stopped before Future completed" của qasync
                if "Event loop stopped before Future completed" in str(e):
                    logger.debug("Event loop đã kết thúc bình thường")
                    exit_code = 0
                else:
                    raise
        else:
            # CLI / TUI / GPIO: asyncio chuẩn
            if args.mode == "tui":
                try:
                    import textual  # noqa: F401
                except ImportError as e:
                    logger.error(
                        "Chế độ TUI yêu cầu textual. Vui lòng chạy:\n"
                        "  uv sync --extra tui\n"
                        "  pip install '.[tui]'\n"
                        "Môi trường không màn hình/SSH vui lòng dùng: python main.py --mode cli\n"
                        f"(Lỗi gốc: {e})"
                    )
                    sys.exit(1)

            # Chế độ CLI / GPIO: asyncio chuẩn; SIGINT yêu cầu TaskManager đóng
            shutdown_state = {"requested": False}

            def handle_sigint_cli(*_):
                if shutdown_state["requested"]:
                    # Ctrl+C lần hai: Buộc dừng thoát ngay
                    logger.warning(
                        "Tiếp tục nhận tín hiệu SIGINT, buộc dừng thoát ngay"
                    )
                    os._exit(130)
                shutdown_state["requested"] = True
                logger.info("Nhận được tín hiệu SIGINT, đang thoát...")
                try:
                    if _container and _container.tasks:
                        _container.tasks.request_shutdown()
                except Exception:
                    pass

            signal.signal(signal.SIGINT, handle_sigint_cli)
            exit_code = asyncio.run(
                start_app(args.mode, args.protocol, args.skip_activation)
            )

    except KeyboardInterrupt:
        logger.info("Chương trình bị ngắt bởi người dùng")
        exit_code = 0
    except Exception as e:
        logger.error(f"Chương trình thoát bất thường: {e}", exc_info=True)
        exit_code = 1
    finally:
        sys.exit(exit_code)
