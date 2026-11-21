"""Recursive filesystem observer with a single debounced writer."""

from pathlib import Path
from queue import Empty, Queue
from threading import Event, Thread
from time import monotonic


class WatchfilesObserver(Thread):
    """Use native recursive notifications, including for moved-in directories."""

    def __init__(self, source, queue):
        from watchfiles import Change, watch

        self.ready = Event()
        self.stopped = Event()

        def run():
            try:
                for changes in watch(source, watch_filter=None, force_polling=False,
                                     stop_event=self.stopped, yield_on_timeout=True, rust_timeout=500):
                    for change, path in changes:
                        path = Path(path)
                        if change == Change.added or (change == Change.modified and not path.is_dir()):
                            queue.put(path)
                    self.ready.set()
            except (OSError, RuntimeError):
                self.ready.set()

        super().__init__(name="StrmMirrorWatchfiles", target=run, daemon=True)

    def stop(self):
        self.stopped.set()


def create_observer(source, queue):
    try:
        return WatchfilesObserver(source, queue)
    except ImportError:
        pass

    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer

    class Changes(FileSystemEventHandler):
        def on_any_event(self, event):
            if event.event_type == "events_lost":
                queue.put(source)
                return
            if event.event_type in {"created", "modified", "closed", "moved"} and (
                not event.is_directory or event.event_type in {"created", "moved"}
            ):
                queue.put(Path(event.dest_path or event.src_path))

    observer = Observer()
    observer.schedule(Changes(), str(source), recursive=True)
    return observer


def summarize(prefix, result):
    return (
        f"{prefix}：新增 STRM {result['created']}，更新 STRM {result['updated']}，"
        f"复制附属文件 {result['sidecars']}，已一致 {result['unchanged']}，"
        f"跳过 {result['skipped']}，失败 {result['errors']}，写入中 {result['pending']}。"
    )


def watch(mirror, stopped, report):
    queue = Queue()
    started = False
    try:
        observer = create_observer(mirror.source, queue)
        observer.start()
        started = True
        if isinstance(observer, WatchfilesObserver) and not observer.ready.wait(timeout=5):
            raise OSError("无法启动 watchfiles")
        if not observer.is_alive():
            raise OSError("文件系统观察器已退出")
        report(f"监听已启动（{type(observer).__name__}），补齐现有目录。")
        result = mirror.scan(stopped)
        report(summarize("实时监听中，首次补齐完成", result))
        while not stopped.is_set():
            try:
                changed = {queue.get(timeout=0.5)}
            except Empty:
                if not observer.is_alive():
                    report("实时监听已中断，请检查源目录并重新启用。")
                    return
                continue

            deadline = monotonic() + 1
            while not stopped.is_set():
                remaining = deadline - monotonic()
                if remaining <= 0:
                    break
                try:
                    changed.add(queue.get(timeout=min(0.25, remaining)))
                except Empty:
                    continue

            result = mirror.sync_changes(changed, stopped)
            if result["pending"] and not stopped.wait(0.5):
                retry = mirror.sync_changes(changed, stopped)
                result["pending"] = retry.pop("pending", 0)
                result.update(retry)
            if any(result[key] for key in ("created", "updated", "sidecars", "errors", "pending")):
                report(summarize("实时监听中，事件处理完成", result))
    except ImportError:
        report("请在容器中提供 watchfiles 或 watchdog。")
    except (OSError, RuntimeError):
        report("无法继续实时监听，请检查源目录、挂载和文件权限。")
    finally:
        if started:
            observer.stop()
            observer.join(timeout=5)
