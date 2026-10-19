"""Quản lý tác vụ (TaskManager).

Quản lý tập trung việc tạo, theo dõi và dọn dẹp các asynchronous task.
"""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from src.logging import get_logger

logger = get_logger()


class TaskManager:
    """Bộ quản lý tác vụ bất đồng bộ.

    Trách nhiệm:
    - Tạo và theo dõi các asynchronous task
    - Hủy đồng loạt tất cả task khi đóng ứng dụng
    - Cung cấp cơ chế lập lịch tác vụ an toàn theo luồng (thread-safe)

    Cách dùng:
        tm = TaskManager()
        tm.set_loop(asyncio.get_running_loop())

        # Tạo task
        task = tm.spawn(some_coroutine(), "task_name")

        # Lập lịch an toàn theo luồng
        tm.schedule_nowait(some_function, arg1, arg2)

        # Dọn dẹp khi tắt
        await tm.cancel_all()
    """

    def __init__(self):
        self._tasks: set[asyncio.Task] = set()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._shutdown_event: asyncio.Event | None = None
        self._running: bool = False

    def initialize(self, loop: asyncio.AbstractEventLoop | None = None) -> None:
        """Khởi tạo bộ quản lý tác vụ.

        Args:
            loop: Event loop, nếu là None sẽ dùng loop đang chạy hiện tại
        """
        self._loop = loop or asyncio.get_running_loop()
        self._shutdown_event = asyncio.Event()
        self._running = True
        logger.debug("TaskManager đã được khởi tạo")

    @property
    def loop(self) -> asyncio.AbstractEventLoop | None:
        """
        Lấy event loop.
        """
        return self._loop

    @property
    def running(self) -> bool:
        """
        Kiểm tra xem có đang chạy hay không.
        """
        return self._running

    @property
    def shutdown_event(self) -> asyncio.Event | None:
        """
        Lấy sự kiện đóng (shutdown event).
        """
        return self._shutdown_event

    def spawn(self, coro: Awaitable[Any], name: str) -> asyncio.Task | None:
        """Tạo task bất đồng bộ và theo dõi.

        Args:
            coro: Đối tượng coroutine
            name: Tên task

        Returns:
            Đối tượng task được tạo, trả về None nếu ứng dụng đang đóng
        """
        # Kiểm tra xem có đang đóng hay không
        if not self._running or (
            self._shutdown_event and self._shutdown_event.is_set()
        ):
            logger.debug(f"Bỏ qua tạo tác vụ (ứng dụng đang đóng): {name}")
            return None

        task = asyncio.create_task(coro, name=name)
        self._tasks.add(task)

        def _on_done(t: asyncio.Task):
            self._tasks.discard(t)
            if not t.cancelled():
                exc = t.exception()
                if exc:
                    # done callback không có active exception context, bắt buộc phải truyền exc instance
                    logger.error(
                        f"Tác vụ {name} kết thúc bất thường: {exc}", exc_info=exc
                    )

        task.add_done_callback(_on_done)
        return task

    def schedule_nowait(self, fn: Callable, *args, **kwargs) -> None:
        """Lập lịch callable một cách an toàn theo luồng (thread-safe).

        Nếu callable trả về một coroutine, task sẽ được tự động tạo.

        Args:
            fn: Đối tượng callable
            *args: Tham số vị trí
            **kwargs: Tham số từ khóa
        """
        # Kiểm tra xem có đang đóng hay không - từ chối trong im lặng
        if not self._running or (
            self._shutdown_event and self._shutdown_event.is_set()
        ):
            return

        if not self._loop or self._loop.is_closed():
            # Bỏ qua trong im lặng khi đang đóng, không in cảnh báo
            return

        def _runner():
            try:
                result = fn(*args, **kwargs)
                if asyncio.iscoroutine(result):
                    task = self.spawn(
                        result, name=f"scheduled:{getattr(fn, '__name__', 'anon')}"
                    )
                    if task is None:
                        result.close()
            except Exception as e:
                logger.error(
                    f"Thực thi callable được lập lịch thất bại: {e}", exc_info=True
                )

        self._loop.call_soon_threadsafe(_runner)

    async def wait_shutdown(self) -> None:
        """
        Chờ tín hiệu đóng.
        """
        if self._shutdown_event:
            await self._shutdown_event.wait()

    def request_shutdown(self) -> None:
        """
        Yêu cầu đóng.
        """
        if self._shutdown_event and not self._shutdown_event.is_set():
            self._shutdown_event.set()
            logger.info("Nhận được yêu cầu đóng")

    async def cancel_all(self) -> None:
        """Hủy tất cả task đang theo dõi.

        Sẽ chờ tất cả task hoàn thành hoặc bị hủy.
        """
        self._running = False

        if self._shutdown_event:
            self._shutdown_event.set()

        if not self._tasks:
            return

        logger.info(f"Đang hủy {len(self._tasks)} tác vụ...")

        # Hủy tất cả task
        for task in list(self._tasks):
            if not task.done():
                task.cancel()

        # Chờ tất cả task hoàn thành
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
            self._tasks.clear()

        logger.info("Tất cả tác vụ đã được hủy")

    def task_count(self) -> int:
        """
        Lấy số lượng task hiện tại.
        """
        return len(self._tasks)

    def get_task_names(self) -> list[str]:
        """
        Lấy danh sách tên của tất cả task.
        """
        return [t.get_name() for t in self._tasks if not t.done()]
