from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

import imageio_ffmpeg
from PySide6.QtCore import QProcess, QTimer, QUrl, Qt
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QFrame, QHBoxLayout, QLabel, QListWidget,
    QMainWindow, QMessageBox, QPushButton, QSlider, QSpinBox, QVBoxLayout,
    QWidget,
)

SUPPORTED = {".mp3", ".wma", ".wav"}


def clock(ms: int) -> str:
    seconds = max(0, ms // 1000)
    return f"{seconds // 60:02}:{seconds % 60:02}"


def ffmpeg_executable() -> str | None:
    executable = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
    base = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent
    bundled = base / executable
    if bundled.is_file():
        return str(bundled)
    try:
        return imageio_ffmpeg.get_ffmpeg_exe()
    except RuntimeError:
        return shutil.which(executable)


class DropListWidget(QListWidget):
    def __init__(self, add_files) -> None:
        super().__init__()
        self.add_files = add_files
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if any(url.isLocalFile() and Path(url.toLocalFile()).suffix.lower() in SUPPORTED
               for url in event.mimeData().urls()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:
        event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        self.add_files(Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile())
        event.acceptProposedAction()


class PlayerWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("hifamily player")
        self.resize(860, 550)
        self.setMinimumSize(720, 500)
        self.setAcceptDrops(True)

        self.audio = QAudioOutput(self)
        self.player = QMediaPlayer(self)
        self.player.setAudioOutput(self.audio)
        self.audio.setVolume(0.75)
        self.paths: list[Path] = []
        self.current = -1
        self.temp = tempfile.TemporaryDirectory(prefix="hifamily-player-")
        self.convert_process: QProcess | None = None
        self.converting = False
        self.play_after_conversion = False
        self.pending_generation = 0
        self.fade_timer = QTimer(self)
        self.fade_timer.setInterval(25)
        self.fade_timer.timeout.connect(self._fade_tick)
        self.fade_start = 0.0
        self.fade_end = 0.0
        self.fade_elapsed = 0
        self.fade_total = 0
        self.fade_action = ""
        self.auto_faded = False
        self.seeking = False

        self._build_ui()
        self._style()
        self.player.durationChanged.connect(self._duration_changed)
        self.player.positionChanged.connect(self._position_changed)
        self.player.mediaStatusChanged.connect(self._media_status)
        self.player.errorOccurred.connect(self._playback_error)

    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(20, 18, 20, 18)
        outer.setSpacing(14)

        header = QHBoxLayout()
        brand = QLabel("hifamily player")
        brand.setObjectName("brand")
        header.addWidget(brand)
        header.addStretch()
        self.add_button = QPushButton("+")
        self.add_button.setObjectName("roundSmall")
        self.add_button.setToolTip("오디오 파일 추가")
        self.add_button.setAccessibleName("파일 추가")
        self.add_button.clicked.connect(self.choose_files)
        header.addWidget(self.add_button)
        outer.addLayout(header)

        display = QFrame()
        display.setObjectName("display")
        display_layout = QVBoxLayout(display)
        display_layout.setContentsMargins(20, 18, 20, 18)
        eyebrow = QLabel("NOW PLAYING")
        eyebrow.setObjectName("eyebrow")
        self.title_label = QLabel("오디오 파일을 끌어 놓거나 + 버튼으로 추가하세요")
        self.title_label.setObjectName("trackTitle")
        self.title_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.title_label.setWordWrap(True)
        self.detail_label = QLabel("재생 가능한 형식: MP3 · WMA · WAV")
        self.detail_label.setObjectName("detail")
        display_layout.addWidget(eyebrow)
        display_layout.addWidget(self.title_label)
        display_layout.addWidget(self.detail_label)
        outer.addWidget(display)

        seek_row = QHBoxLayout()
        self.elapsed = QLabel("00:00")
        self.seek = QSlider(Qt.Horizontal)
        self.seek.setRange(0, 0)
        self.seek.sliderPressed.connect(lambda: setattr(self, "seeking", True))
        self.seek.sliderReleased.connect(self._seek_released)
        self.total = QLabel("00:00")
        seek_row.addWidget(self.elapsed)
        seek_row.addWidget(self.seek, 1)
        seek_row.addWidget(self.total)
        outer.addLayout(seek_row)

        controls = QHBoxLayout()
        self.prev_button = QPushButton("◀◀")
        self.play_button = QPushButton("▶")
        self.play_button.setObjectName("primary")
        self.stop_button = QPushButton("■")
        self.next_button = QPushButton("▶▶")
        for button in (self.prev_button, self.play_button, self.stop_button, self.next_button):
            button.setProperty("roundControl", True)
            controls.addWidget(button)
        for button, name in ((self.prev_button, "이전 곡"), (self.play_button, "재생 또는 일시정지"),
                             (self.stop_button, "정지"), (self.next_button, "다음 곡")):
            button.setToolTip(name)
            button.setAccessibleName(name)
        self.prev_button.clicked.connect(self.previous_track)
        self.play_button.clicked.connect(self.toggle_play)
        self.stop_button.clicked.connect(self.stop_with_fade)
        self.next_button.clicked.connect(self.next_track)
        controls.addStretch()
        controls.addWidget(QLabel("VOL"))
        self.volume = QSlider(Qt.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setValue(75)
        self.volume.setFixedWidth(115)
        self.volume.valueChanged.connect(self._volume_changed)
        controls.addWidget(self.volume)
        outer.addLayout(controls)

        fades = QHBoxLayout()
        fades.addWidget(QLabel("페이드 시간"))
        self.fade_seconds = QSpinBox()
        self.fade_seconds.setRange(0, 10)
        self.fade_seconds.setValue(3)
        self.fade_seconds.setSuffix(" 초")
        fades.addWidget(self.fade_seconds)
        self.fade_in_button = QPushButton("↗")
        self.fade_out_button = QPushButton("↘")
        for button, name in ((self.fade_in_button, "페이드 인"), (self.fade_out_button, "페이드 아웃")):
            button.setObjectName("roundSmall")
            button.setToolTip(name)
            button.setAccessibleName(name)
        self.fade_in_button.clicked.connect(self.fade_in)
        self.fade_out_button.clicked.connect(self.fade_out)
        fades.addWidget(self.fade_in_button)
        fades.addWidget(QLabel("페이드 인"))
        fades.addWidget(self.fade_out_button)
        fades.addWidget(QLabel("페이드 아웃"))
        fades.addStretch()
        outer.addLayout(fades)

        list_header = QHBoxLayout()
        list_header.addWidget(QLabel("재생목록"))
        list_header.addStretch()
        remove = QPushButton("−")
        remove.setObjectName("roundSmall")
        remove.setToolTip("선택한 파일 삭제")
        remove.setAccessibleName("선택 삭제")
        remove.clicked.connect(self.remove_selected)
        list_header.addWidget(remove)
        outer.addLayout(list_header)
        self.drop_hint = QLabel("여기에 파일을 끌어 놓으세요  ·  재생 가능: MP3 / WMA / WAV")
        self.drop_hint.setObjectName("dropHint")
        outer.addWidget(self.drop_hint)
        self.list_widget = DropListWidget(self.add_files)
        self.list_widget.itemDoubleClicked.connect(lambda item: self.load_track(self.list_widget.row(item)))
        outer.addWidget(self.list_widget, 1)
        self.status = QLabel("MP3, WMA, WAV 파일을 추가하면 재생할 수 있습니다")
        self.status.setObjectName("status")
        outer.addWidget(self.status)

    def _style(self) -> None:
        self.setStyleSheet("""
            QMainWindow, QWidget { background: #10151c; color: #e8edf2; font-size: 13px; }
            QLabel#brand { color: #77e5cf; font-size: 19px; font-weight: 800; letter-spacing: 2px; }
            QLabel#eyebrow { color: #77e5cf; font-size: 10px; font-weight: 700; letter-spacing: 2px; }
            QLabel#trackTitle { font-size: 23px; font-weight: 700; }
            QLabel#detail, QLabel#status { color: #9aaab7; }
            QFrame#display { background: #1b2631; border: 1px solid #30434f; border-radius: 12px; }
            QFrame#display QLabel { background: transparent; }
            QPushButton { background: #263641; border: 1px solid #3c5660; border-radius: 7px;
                          padding: 9px 13px; min-height: 18px; }
            QPushButton:hover { background: #36515b; }
            QPushButton:pressed { background: #1b7774; }
            QPushButton[roundControl="true"] { min-width: 54px; max-width: 54px;
                min-height: 54px; max-height: 54px; padding: 0; border-radius: 28px;
                font-size: 15px; font-weight: 700; }
            QPushButton#roundSmall { min-width: 36px; max-width: 36px;
                min-height: 36px; max-height: 36px; padding: 0; border-radius: 19px;
                font-size: 18px; font-weight: 700; }
            QPushButton#primary { background: #46c7b2; color: #09201f; font-weight: 700; border: 0; }
            QPushButton#primary:hover { background: #78dec9; }
            QLabel#dropHint { color: #a9c2c9; background: #17212b;
                border: 1px dashed #53727c; border-radius: 7px; padding: 8px; }
            QListWidget { background: #17212b; border: 1px solid #30434f; border-radius: 8px;
                          padding: 5px; outline: 0; }
            QListWidget::item { padding: 7px; border-radius: 4px; }
            QListWidget::item:selected { background: #286d71; }
            QSpinBox { background: #263641; border: 1px solid #3c5660; border-radius: 5px;
                       padding: 6px; min-width: 65px; }
            QSlider::groove:horizontal { height: 5px; background: #344854; border-radius: 2px; }
            QSlider::handle:horizontal { width: 14px; margin: -5px 0; background: #77e5cf;
                                         border-radius: 7px; }
        """)

    def choose_files(self) -> None:
        names, _ = QFileDialog.getOpenFileNames(
            self, "오디오 파일 추가", "", "오디오 파일 (*.mp3 *.wma *.wav)"
        )
        self.add_files(Path(name) for name in names)

    def add_files(self, files) -> None:
        added = 0
        for path in files:
            path = Path(path)
            if path.is_file() and path.suffix.lower() in SUPPORTED:
                self.paths.append(path)
                self.list_widget.addItem(path.name)
                added += 1
        if added:
            self.status.setText(f"{added}개 파일 추가됨")
            if self.current < 0:
                self.load_track(0, autoplay=False)
        else:
            self.status.setText("추가 가능한 오디오 형식: MP3, WMA, WAV")

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if any(url.isLocalFile() and Path(url.toLocalFile()).suffix.lower() in SUPPORTED
               for url in event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        self.add_files(Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile())
        event.acceptProposedAction()

    def load_track(self, index: int, autoplay: bool = True) -> None:
        if not 0 <= index < len(self.paths):
            return
        self.pending_generation += 1
        generation = self.pending_generation
        if self.convert_process and self.convert_process.state() != QProcess.NotRunning:
            self.convert_process.kill()
        self.convert_process = None
        self.converting = False
        self.play_after_conversion = False
        self._cancel_fade()
        self.player.stop()
        self.player.setSource(QUrl())
        self.current = index
        self.auto_faded = False
        path = self.paths[index]
        self.list_widget.setCurrentRow(index)
        self.title_label.setText(path.stem)
        self.detail_label.setText(f"{path.suffix[1:].upper()}  ·  {path.parent}")
        self.play_button.setText("▶")
        self.elapsed.setText("00:00")
        self.total.setText("00:00")
        self.seek.setRange(0, 0)
        if path.suffix.lower() == ".wma":
            self._convert_wma(path, generation, autoplay)
        else:
            self.player.setSource(QUrl.fromLocalFile(str(path)))
            self.status.setText(f"준비됨: {path.name}")
            if autoplay:
                self._start_playback()

    def _convert_wma(self, path: Path, generation: int, autoplay: bool) -> None:
        ffmpeg = ffmpeg_executable()
        if not ffmpeg:
            self.status.setText("WMA 재생에는 FFmpeg가 필요합니다")
            QMessageBox.warning(self, "FFmpeg 필요", "WMA 재생을 위해 FFmpeg를 설치하고 PATH에 추가하세요.")
            return
        target = Path(self.temp.name) / f"track-{generation}.wav"
        self.converting = True
        self.play_after_conversion = autoplay
        process = QProcess(self)
        self.convert_process = process
        process.setProgram(ffmpeg)
        process.setArguments(["-v", "error", "-y", "-i", str(path), "-vn", "-c:a", "pcm_s16le", str(target)])
        process.finished.connect(lambda code, status: self._conversion_done(generation, code, target, autoplay))
        process.finished.connect(process.deleteLater)
        process.start()
        self.status.setText(f"WMA 변환 중: {path.name}")

    def _conversion_done(self, generation: int, code: int, target: Path, autoplay: bool) -> None:
        if generation != self.pending_generation:
            return
        self.converting = False
        self.convert_process = None
        if code != 0 or not target.is_file():
            self.status.setText("WMA 변환 실패")
            QMessageBox.warning(self, "재생 실패", "WMA 파일을 디코딩하지 못했습니다. 파일과 FFmpeg를 확인하세요.")
            return
        self.player.setSource(QUrl.fromLocalFile(str(target)))
        self.status.setText(f"준비됨: {self.paths[self.current].name}")
        if self.play_after_conversion:
            self._start_playback()

    def _start_playback(self) -> None:
        self._cancel_fade()
        self.auto_faded = False
        self.audio.setVolume(0.0)
        self.player.play()
        self.play_button.setText("Ⅱ")
        self._begin_fade(self.volume.value() / 100, "")
        self.status.setText("페이드 인" if self.fade_seconds.value() else "재생 중")

    def toggle_play(self) -> None:
        if self.current < 0:
            self.choose_files()
            return
        if self.converting:
            self.play_after_conversion = True
            self.status.setText("변환 후 재생합니다")
            return
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self._cancel_fade()
            self.player.pause()
            self.play_button.setText("▶")
            self.status.setText("일시정지")
        elif self.player.source().isEmpty():
            self.load_track(self.current)
        else:
            self._start_playback()

    def stop_with_fade(self) -> None:
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self._begin_fade(0.0, "stop")
        else:
            self._stop_now()

    def _stop_now(self) -> None:
        self._cancel_fade()
        self.player.stop()
        self.audio.setVolume(self.volume.value() / 100)
        self.play_button.setText("▶")
        self.status.setText("정지")

    def fade_in(self) -> None:
        if self.converting:
            self.play_after_conversion = True
            self.status.setText("변환 후 페이드 인합니다")
            return
        if self.player.playbackState() != QMediaPlayer.PlayingState:
            if self.current >= 0:
                self._start_playback()
            return
        self.audio.setVolume(0.0)
        self._begin_fade(self.volume.value() / 100, "")
        self.status.setText("페이드 인" if self.fade_seconds.value() else "재생 중")

    def fade_out(self) -> None:
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self._begin_fade(0.0, "pause")
            self.status.setText("페이드 아웃")

    def _begin_fade(self, end: float, action: str) -> None:
        self.fade_timer.stop()
        self.fade_start = self.audio.volume()
        self.fade_end = end
        self.fade_elapsed = 0
        self.fade_total = self.fade_seconds.value() * 1000
        self.fade_action = action
        if self.fade_total == 0:
            self.audio.setVolume(end)
            self._finish_fade()
        else:
            self.fade_timer.start()

    def _fade_tick(self) -> None:
        self.fade_elapsed = min(self.fade_total, self.fade_elapsed + self.fade_timer.interval())
        ratio = self.fade_elapsed / self.fade_total
        self.audio.setVolume(self.fade_start + (self.fade_end - self.fade_start) * ratio)
        if self.fade_elapsed >= self.fade_total:
            self.fade_timer.stop()
            self._finish_fade()

    def _finish_fade(self) -> None:
        action = self.fade_action
        self.fade_action = ""
        if action == "stop":
            self._stop_now()
        elif action == "pause":
            self.player.pause()
            self.play_button.setText("▶")
            self.status.setText("페이드 아웃 완료 · 일시정지")
        elif action == "next":
            self.next_track()
        elif action == "end":
            self.player.pause()
            self.next_track()
        else:
            self.status.setText("재생 중")

    def _cancel_fade(self) -> None:
        self.fade_timer.stop()
        self.fade_action = ""

    def _volume_changed(self, value: int) -> None:
        if not self.fade_timer.isActive():
            self.audio.setVolume(value / 100)

    def previous_track(self) -> None:
        if self.current > 0:
            self.load_track(self.current - 1)
        elif self.current == 0:
            self.player.setPosition(0)

    def next_track(self) -> None:
        if self.current + 1 < len(self.paths):
            self.load_track(self.current + 1)
        else:
            self._stop_now()

    def remove_selected(self) -> None:
        row = self.list_widget.currentRow()
        if row < 0:
            return
        self.paths.pop(row)
        self.list_widget.takeItem(row)
        if row == self.current:
            self.pending_generation += 1
            if self.convert_process and self.convert_process.state() != QProcess.NotRunning:
                self.convert_process.kill()
            self.converting = False
            self.play_after_conversion = False
            self._stop_now()
            self.player.setSource(QUrl())
            self.current = -1
            self.title_label.setText("오디오 파일을 끌어 놓거나 + 버튼으로 추가하세요")
            self.detail_label.setText("재생 가능한 형식: MP3 · WMA · WAV")
        elif row < self.current:
            self.current -= 1
        if self.current < 0 and self.paths:
            self.load_track(min(row, len(self.paths) - 1), autoplay=False)

    def _duration_changed(self, duration: int) -> None:
        self.seek.setRange(0, duration)
        self.total.setText(clock(duration))

    def _position_changed(self, position: int) -> None:
        if not self.seeking:
            self.seek.setValue(position)
        self.elapsed.setText(clock(position))
        duration = self.player.duration()
        fade_ms = self.fade_seconds.value() * 1000
        if (duration > 0 and fade_ms > 0 and not self.auto_faded
                and not self.fade_timer.isActive()
                and self.player.playbackState() == QMediaPlayer.PlayingState
                and position >= max(0, duration - fade_ms - 250)):
            self.auto_faded = True
            self._begin_fade(0.0, "end")

    def _seek_released(self) -> None:
        self.player.setPosition(self.seek.value())
        self.seeking = False
        self.auto_faded = False

    def _media_status(self, status: QMediaPlayer.MediaStatus) -> None:
        if status == QMediaPlayer.EndOfMedia and not self.fade_timer.isActive():
            self.next_track()

    def _playback_error(self, error: QMediaPlayer.Error, message: str) -> None:
        if error != QMediaPlayer.NoError:
            self.status.setText(f"재생 오류: {message}")

    def closeEvent(self, event) -> None:
        self._cancel_fade()
        self.player.stop()
        if self.convert_process and self.convert_process.state() != QProcess.NotRunning:
            self.convert_process.kill()
            self.convert_process.waitForFinished(1000)
        self.player.setSource(QUrl())
        self.temp.cleanup()
        super().closeEvent(event)


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("hifamily player")
    window = PlayerWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
