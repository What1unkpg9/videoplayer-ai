# main.py
# --- PORTABLE BOOTSTRAP (Must be before ANY other imports) ---
import sys
import os
import ctypes.util

if getattr(sys, 'frozen', False):
    # Мы внутри собранного PyInstaller бинарника
    # sys._MEIPASS — временная папка, куда PyInstaller распаковал ресурсы
    base_path = sys._MEIPASS
    
    # Структура внутри бинарника, которую создаст build.py:
    # _MEIPASS/vlc_libs/          -> libvlc.so, libvlccore.so, vlc.dll, plugins/
    # _MEIPASS/vlc_libs/plugins/  -> ВАЖНО: без папки plugins VLC не играет форматы
    vlc_lib_dir = os.path.join(base_path, 'vlc_libs')
    vlc_plugin_dir = os.path.join(vlc_lib_dir, 'plugins')

    # 1. Настраиваем пути поиска библиотек ОС
    if sys.platform == 'win32':
        # Windows: добавляем папку с DLL в PATH и используем add_dll_directory (Python 3.8+)
        os.environ['PATH'] = vlc_lib_dir + os.pathsep + os.environ.get('PATH', '')
        if hasattr(os, 'add_dll_directory'):
            try: os.add_dll_directory(vlc_lib_dir)
            except Exception: pass
    else:
        # Linux / macOS: LD_LIBRARY_PATH / DYLD_LIBRARY_PATH
        os.environ['LD_LIBRARY_PATH'] = vlc_lib_dir + os.pathsep + os.environ.get('LD_LIBRARY_PATH', '')
        if sys.platform == 'darwin':
            os.environ['DYLD_LIBRARY_PATH'] = vlc_lib_dir + os.pathsep + os.environ.get('DYLD_LIBRARY_PATH', '')

    # 2. Явно указываем VLC, где лежат плагины (декодеры, демуксеры, видео-вывод)
    # Это КРИТИЧЕСКИ ВАЖНО. Без этого VLC инициализируется, но media_new вернет ошибку "No suitable decoder module".
    os.environ['VLC_PLUGIN_PATH'] = vlc_plugin_dir

    # 3. Монки-патчим ctypes.util.find_library, который использует python-vlc для поиска libvlc
    _original_find_library = ctypes.util.find_library
    def _patched_find_library(name: str):
        # python-vlc ищет 'vlc' и 'vlccore'
        if name in ('vlc', 'vlccore'):
            # Формируем имя файла под платформу
            if sys.platform == 'win32':
                lib_name = f'{name}.dll'
            elif sys.platform == 'darwin':
                lib_name = f'lib{name}.dylib'
            else: # linux, bsd
                lib_name = f'lib{name}.so'
            
            candidate = os.path.join(vlc_lib_dir, lib_name)
            if os.path.exists(candidate):
                return candidate
        return _original_find_library(name)
    
    ctypes.util.find_library = _patched_find_library

# --- END BOOTSTRAP ---

import platform
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QSlider, QFileDialog, QStyle, QLabel, QTextEdit,
    QDockWidget, QMessageBox
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFontDatabase

# Теперь импорт vlc безопасен — он найдет наши библиотеки
import vlc


class MediaPlayer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Portable VLC Player")
        self.resize(1000, 600)

        # VLC Instance: --no-xlib критичен для Linux+Qt
        # --quiet убирает спам в консоль
        self.instance = vlc.Instance("--no-xlib", "--quiet")
        self.player = self.instance.media_player_new()
        self.media = None

        self._setup_ui()
        self._setup_vlc_video_output()
        
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self._update_ui_timer)
        self._slider_pressed = False

    def _setup_ui(self):
        self.video_widget = QWidget()
        self.video_widget.setStyleSheet("background-color: #1a1a1a;")
        self.video_widget.setMinimumSize(640, 360)

        self.btn_open = QPushButton("Открыть файл")
        self.btn_open.clicked.connect(self.open_file)
        self.btn_open.setIcon(self.style().standardIcon(QStyle.SP_DirOpenIcon))

        self.btn_play = QPushButton()
        self.btn_play.setEnabled(False)
        self.btn_play.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
        self.btn_play.clicked.connect(self.toggle_play)

        self.slider_time = QSlider(Qt.Horizontal)
        self.slider_time.setRange(0, 0)
        self.slider_time.sliderPressed.connect(lambda: setattr(self, '_slider_pressed', True))
        self.slider_time.sliderReleased.connect(self._on_slider_released)
        self.slider_time.sliderMoved.connect(self._on_slider_moved)

        self.lbl_time = QLabel("00:00:00 / 00:00:00")
        self.lbl_time.setMinimumWidth(160)
        self.lbl_time.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        controls_layout = QHBoxLayout()
        controls_layout.addWidget(self.btn_open)
        controls_layout.addWidget(self.btn_play)
        controls_layout.addWidget(self.slider_time, 1)
        controls_layout.addWidget(self.lbl_time)

        central_layout = QVBoxLayout()
        central_layout.addWidget(self.video_widget, 1)
        central_layout.addLayout(controls_layout)
        
        central_widget = QWidget()
        central_widget.setLayout(central_layout)
        self.setCentralWidget(central_widget)

        # Dock: Media Info
        self.info_text = QTextEdit()
        self.info_text.setReadOnly(True)
        self.info_text.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        self.info_text.setLineWrapMode(QTextEdit.NoWrap)
        
        dock = QDockWidget("Информация о медиафайле (Media Info)", self)
        dock.setWidget(self.info_text)
        dock.setAllowedAreas(Qt.RightDockWidgetArea | Qt.LeftDockWidgetArea)
        self.addDockWidget(Qt.RightDockWidgetArea, dock)
        dock.hide()
        self.dock_info = dock

    def _setup_vlc_video_output(self):
        win_id = int(self.video_widget.winId())
        sys_name = platform.system()
        try:
            if sys_name == "Linux":
                self.player.set_xwindow(win_id)
            elif sys_name == "Windows":
                self.player.set_hwnd(win_id)
            elif sys_name == "Darwin":
                self.player.set_nsobject(win_id)
        except Exception as e:
            QMessageBox.critical(self, "VLC Video Error", f"Failed to bind video window:\n{e}")

    def open_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Открыть медиафайл", "", 
            "Media Files (*.mp4 *.mkv *.avi *.mov *.flv *.mp3 *.flac *.wav *.opus *.webm *.ts *.m4v);;All Files (*)"
        )
        if not path: return

        self._reset_state()
        self.media = self.instance.media_new(path)
        self.player.set_media(self.media)
        
        # Парсим метаданные синхронно
        self.media.parse() 
        
        self._populate_media_info()
        self.dock_info.show()
        
        self.player.play()
        self.timer.start()
        self.btn_play.setEnabled(True)
        self._update_play_button_icon()

    def _reset_state(self):
        self.timer.stop()
        self.slider_time.setValue(0)
        self.slider_time.setRange(0, 0)
        self.lbl_time.setText("00:00:00 / 00:00:00")
        self.info_text.clear()
        if self.media:
            self.media.release()
            self.media = None

    def toggle_play(self):
        if not self.media: return
        if self.player.is_playing(): self.player.pause()
        else: self.player.play()
        self._update_play_button_icon()

    def _update_play_button_icon(self):
        icon = QStyle.SP_MediaPause if self.player.is_playing() else QStyle.SP_MediaPlay
        self.btn_play.setIcon(self.style().standardIcon(icon))

    def _update_ui_timer(self):
        if not self.media or self._slider_pressed: return
        length = self.player.get_length()
        time = self.player.get_time()
        if length > 0:
            self.slider_time.setRange(0, length)
            self.slider_time.setValue(time)
        self.lbl_time.setText(f"{self._fmt_time(time)} / {self._fmt_time(length)}")
        if time >= length > 0 and not self.player.is_playing():
            self.timer.stop()
            self._update_play_button_icon()

    def _on_slider_moved(self, pos):
        if self._slider_pressed:
            self.lbl_time.setText(f"{self._fmt_time(pos)} / {self._fmt_time(self.slider_time.maximum())}")

    def _on_slider_released(self):
        self.player.set_time(self.slider_time.value())
        self._slider_pressed = False

    @staticmethod
    def _fmt_time(ms):
        if ms < 0: ms = 0
        s = ms // 1000
        h, r = divmod(s, 3600)
        m, s = divmod(r, 60)
        return f"{h:02d}:{m:02d}:{s:02d}"

    def _populate_media_info(self):
        if not self.media: return
        lines = []
        meta = self.media
        
        lines.append("=== GENERAL METADATA ===")
        meta_map = {
            vlc.Meta.Title: "Title", vlc.Meta.Artist: "Artist", vlc.Meta.Genre: "Genre",
            vlc.Meta.Copyright: "Copyright", vlc.Meta.Album: "Album", vlc.Meta.TrackNumber: "Track #",
            vlc.Meta.Description: "Description", vlc.Meta.Date: "Date", vlc.Meta.URL: "URL",
            vlc.Meta.Language: "Language", vlc.Meta.Publisher: "Publisher", vlc.Meta.EncodedBy: "Encoded By",
        }
        for key, label in meta_map.items():
            val = meta.get_meta(key)
            if val: lines.append(f"{label:15}: {val}")
        
        dur = meta.get_duration()
        if dur > 0: lines.append(f"{'Duration':15}: {self._fmt_time(dur)} ({dur} ms)")

        lines.append("\n=== TRACKS INFO ===")
        tracks_info = []
        if hasattr(meta, 'get_tracks_info'): tracks_info = meta.get_tracks_info()
        elif hasattr(meta, 'tracks_get'): tracks_info = meta.tracks_get()
        
        if not tracks_info:
            lines.append("No track info (libvlc < 3.0 or parse failed).")
        else:
            for i, t in enumerate(tracks_info):
                lines.append(f"\n--- Track #{i} ---")
                t_type = t.get('type', 'unknown')
                lines.append(f"{'Type':15}: {t_type}")
                lines.append(f"{'Codec (FourCC)':15}: {t.get('codec', 'N/A')}")
                lines.append(f"{'Codec Name':15}: {t.get('codec_name', 'N/A')}")
                lines.append(f"{'Language':15}: {t.get('language', 'N/A')}")
                lines.append(f"{'Bitrate':15}: {self._fmt_bitrate(t.get('bitrate', 0))}")
                lines.append(f"{'ID':15}: {t.get('id', 'N/A')}")

                if t_type == 'video':
                    lines.append(f"{'Resolution':15}: {t.get('width', 0)}x{t.get('height', 0)}")
                    num, den = t.get('frame_rate_num', 0), t.get('frame_rate_den', 1)
                    if num and den: lines.append(f"{'Frame Rate':15}: {num/den:.3f} FPS ({num}/{den})")
                elif t_type == 'audio':
                    lines.append(f"{'Sample Rate':15}: {t.get('rate', 0)} Hz")
                    lines.append(f"{'Channels':15}: {t.get('channels', 0)}")

        self.info_text.setPlainText("\n".join(lines))
        self.info_text.moveCursor(self.info_text.textCursor().Start)

    @staticmethod
    def _fmt_bitrate(bps):
        if not bps: return "N/A"
        if bps >= 1_000_000: return f"{bps/1_000_000:.2f} Mbps"
        if bps >= 1_000: return f"{bps/1_000:.1f} Kbps"
        return f"{bps} bps"

    def closeEvent(self, event):
        self.timer.stop()
        if self.player: self.player.stop(); self.player.release()
        if self.instance: self.instance.release()
        super().closeEvent(event)


def main():
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    player = MediaPlayer()
    player.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
