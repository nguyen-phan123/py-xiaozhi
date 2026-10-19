"""Resource pool.

Cơ chế đăng ký và giải phóng tài nguyên tập trung. Tất cả tài nguyên cần dọn dẹp (tiện ích mở rộng C, audio stream, kết nối mạng, v.v.)
được đăng ký vào pool, khi shutdown sẽ giải phóng đồng loạt theo thứ tự ngược lại lúc đăng ký, tránh giải phóng lặp lại hoặc bỏ sót.
"""

import asyncio
from typing import Awaitable, Callable, Union

from src.logging import get_logger

logger = get_logger()

CleanupFunc = Callable[[], Union[None, Awaitable[None]]]


class ResourcePool:
    """Resource pool — Đăng ký các hàm dọn dẹp, giải phóng đồng loạt theo thứ tự ngược lại.

    Cách dùng:
        pool = ResourcePool()
        pool.register("opus_codec", opus_codec.close)
        pool.register("audio_stream", stream_manager.stop)
        await pool.shutdown()  # Thực thi tất cả hàm dọn dẹp theo thứ tự ngược lại
    """

    def __init__(self):
        self._resources: list[tuple[str, CleanupFunc]] = []
        self._shutting_down = False

    def register(self, name: str, cleanup: CleanupFunc) -> None:
        """Đăng ký một hàm dọn dẹp.

        Args:
            name: Tên tài nguyên (dùng cho log và gỡ lỗi)
            cleanup: Hàm dọn dẹp, có thể là hàm thông thường hoặc async function
        """
        if self._shutting_down:
            logger.warning(f"Resource pool đang đóng, bỏ qua đăng ký: {name}")
            return
        self._resources.append((name, cleanup))

    async def shutdown(self) -> None:
        """Giải phóng tất cả tài nguyên đã đăng ký, thực thi theo thứ tự ngược với lúc đăng ký."""
        if self._shutting_down:
            return
        self._shutting_down = True

        for name, cleanup in reversed(self._resources):
            try:
                result = cleanup()
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.error(f"Giải phóng tài nguyên thất bại [{name}]: {e}", exc_info=True)

        self._resources.clear()
        logger.debug("Resource pool đã được dọn sạch")
