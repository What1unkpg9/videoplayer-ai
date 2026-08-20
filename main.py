# main.py
import sys
import platform
import vlc
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QSlider, QFileDialog, QStyle, QLabel, QTextEdit,
    QDockWidget, QMessageBox
)
from PyQt5.QtCore import Qt, QTimer, QUrl
from PyQt5.QtGui import QIcon, Font, QFontDatabase

class MediaPlayer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("VLC Python Player")
        self.resize(1000, 600)

        # --- VLC Core ---
        # Аргументы: --no-xlib критически важен для Linux + Qt (избегает дедлоков X11)
        self.instance = vlc.Instance("--no-xlib", "--quiet")
        self.player = self.instance.media_player_new()
        self.media = None

        # --- UI Setup ---
        self._setup_ui()
        self._setup_vlc_video_output()
        
        # Таймер для обновления слайдера времени (100мс)
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self._update_ui_timer)
        
        # Флаг, чтобы не дергать setPosition при ручном движении слайдера
        self._slider_pressed = False

    def _setup_ui(self):
        # 1. Видео-виджет (черный фон)
        self.video_widget = QWidget()
        self.video_widget.setStyleSheet("background-color: black;")
        self.video_widget.setMinimumSize(640, 360)

        # 2. Контролы
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

        # 3. Центральный виджет
        central_layout = QVBoxLayout()
        central_layout.addWidget(self.video_widget, 1)
        central_layout.addLayout(controls_layout)
        
        central_widget = QWidget()
        central_widget.setLayout(central_layout)
        self.setCentralWidget(central_widget)

        # 4. Док-виджет "Информация о медиафайле"
        self.info_text = QTextEdit()
        self.info_text.setReadOnly(True)
        self.info_text.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        self.info_text.setLineWrapMode(QTextEdit.NoWrap)
        
        dock = QDockWidget("Информация о медиафайле (Media Info)", self)
        dock.setWidget(self.info_text)
        dock.setAllowedAreas(Qt.RightDockWidgetArea | Qt.LeftDockWidgetArea)
        self.addDockWidget(Qt.RightDockWidgetArea, dock)
        
        # Скрываем док по умолчанию, покажем при загрузке файла
        dock.hide()
        self.dock_info = dock

    def _setup_vlc_video_output(self):
        """Кроссплатформенная привязка окна вывода видео к VLC."""
        win_id = int(self.video_widget.winId())
        sys_name = platform.system()
        
        try:
            if sys_name == "Linux":      # X11 / Wayland (через XWayland)
                self.player.set_xwindow(win_id)
            elif sys_name == "Windows":
                self.player.set_hwnd(win_id)
            elif sys_name == "Darwin":   # macOS (Cocoa)
                self.player.set_nsobject(win_id)
            else:
                print(f"Warning: Unknown platform {sys_name}, video may not render.")
        except Exception as e:
            QMessageBox.critical(self, "VLC Video Error", f"Failed to bind video window:\n{e}")

    # --- File Handling ---
    def open_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Открыть медиафайл", "", 
            "Media Files (*.mp4 *.mkv *.avi *.mov *.flv *.mp3 *.flac *.wav *.opus *.webm);;All Files (*)"
        )
        if not path:
            return

        self._reset_state()
        self.media = self.instance.media_new(path)
        self.player.set_media(self.media)
        
        # Парсим медиа синхронно, чтобы получить треки до старта (опционально, но надежнее)
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

    # --- Playback Control ---
    def toggle_play(self):
        if not self.media:
            return
        if self.player.is_playing():
            self.player.pause()
        else:
            self.player.play()
        self._update_play_button_icon()

    def _update_play_button_icon(self):
        icon = QStyle.SP_MediaPause if self.player.is_playing() else QStyle.SP_MediaPlay
        self.btn_play.setIcon(self.style().standardIcon(icon))

    # --- Slider & Timer ---
    def _update_ui_timer(self):
        if not self.media or self._slider_pressed:
            return
        
        length = self.player.get_length()  # ms
        time = self.player.get_time()      # ms
        
        if length > 0:
            self.slider_time.setRange(0, length)
            self.slider_time.setValue(time)
        
        self.lbl_time.setText(f"{self._fmt_time(time)} / {self._fmt_time(length)}")
        
        # Автостоп в конце (VLC иногда не ставит paused state сразу)
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

    # --- Media Info Parsing (The Core Logic) ---
    def _populate_media_info(self):
        if not self.media:
            return

        lines = []
        meta = self.media
        
        # 1. General Metadata (Title, Artist, etc.)
        lines.append("=== GENERAL METADATA ===")
        meta_map = {
            vlc.Meta.Title: "Title",
            vlc.Meta.Artist: "Artist",
            vlc.Meta.Genre: "Genre",
            vlc.Meta.Copyright: "Copyright",
            vlc.Meta.Album: "Album",
            vlc.Meta.TrackNumber: "Track #",
            vlc.Meta.Description: "Description",
            vlc.Meta.Date: "Date",
            vlc.Meta.Setting: "Setting",
            vlc.Meta.URL: "URL",
            vlc.Meta.Language: "Language",
            vlc.Meta.NowPlaying: "Now Playing",
            vlc.Meta.Publisher: "Publisher",
            vlc.Meta.EncodedBy: "Encoded By",
            vlc.Meta.ArtworkURL: "Artwork URL",
            vlc.Meta.TrackID: "Track ID",
        }
        for key, label in meta_map.items():
            val = meta.get_meta(key)
            if val:
                lines.append(f"{label:15}: {val}")
        
        # Duration from meta (sometimes more accurate) or player
        duration_ms = meta.get_duration()
        if duration_ms > 0:
            lines.append(f"{'Duration':15}: {self._fmt_time(duration_ms)} ({duration_ms} ms)")

        lines.append("\n=== TRACKS INFO (get_tracks_info) ===")
        
        # 2. Deep Track Info (Codecs, Resolution, Bitrate, FPS)
        # get_tracks_info() возвращает список словарей. Требует libvlc >= 3.0
        tracks = meta.tracks_get() # Deprecated name in some bindings, usually media.get_tracks_info() or media.tracks_get()
        # python-vlc использует media.get_tracks_info() или media.tracks_get()
        # Проверим оба варианта для совместимости
        tracks_info = []
        if hasattr(meta, 'get_tracks_info'):
            tracks_info = meta.get_tracks_info()
        elif hasattr(meta, 'tracks_get'):
            tracks_info = meta.tracks_get()
        
        if not tracks_info:
            lines.append("No track info available (libvlc < 3.0 or parse failed).")
        else:
            for i, track in enumerate(tracks_info):
                lines.append(f"\n--- Track #{i} ---")
                # Общие поля
                t_type = track.get('type', 'unknown')
                lines.append(f"{'Type':15}: {t_type}")
                lines.append(f"{'Codec (FourCC)':15}: {track.get('codec', 'N/A')}")
                lines.append(f"{'Codec Name':15}: {track.get('codec_name', 'N/A')}")
                lines.append(f"{'Language':15}: {track.get('language', 'N/A')}")
                lines.append(f"{'Bitrate':15}: {self._fmt_bitrate(track.get('bitrate', 0))}")
                lines.append(f"{'ID':15}: {track.get('id', 'N/A')}")

                if t_type == 'video':
                    lines.append(f"{'Resolution':15}: {track.get('width', 0)}x{track.get('height', 0)}")
                    # FPS приходит как числитель/знаменатель
                    num = track.get('frame_rate_num', 0)
                    den = track.get('frame_rate_den', 1)
                    if num and den:
                        fps = num / den
                        lines.append(f"{'Frame Rate':15}: {fps:.3f} FPS ({num}/{den})")
                    else:
                        lines.append(f"{'Frame Rate':15}: N/A")
                    
                    # Доп. видео параметры
                    if 'sar_num' in track and 'sar_den' in track:
                        lines.append(f"{'SAR':15}: {track['sar_num']}/{track['sar_den']}")
                
                elif t_type == 'audio':
                    lines.append(f"{'Sample Rate':15}: {track.get('rate', 0)} Hz")
                    lines.append(f"{'Channels':15}: {track.get('channels', 0)}")
                    # Bits per sample (глубина)
                    if 'block_align' in track: # иногда есть
                        pass 
                
                elif t_type == 'subpicture' or t_type == 'subtitle':
                    lines.append(f"{'Encoding':15}: {track.get('encoding', 'N/A')}")

        self.info_text.setPlainText("\n".join(lines))
        # Скролл в начало
        self.info_text.moveCursor(self.info_text.textCursor().Start)

    @staticmethod
    def _fmt_bitrate(bps):
        if not bps: return "N/A"
        if bps >= 1_000_000: return f"{bps/1_000_000:.2f} Mbps"
        if bps >= 1_000: return f"{bps/1_000:.1f} Kbps"
        return f"{bps} bps"

    def closeEvent(self, event):
        self.timer.stop()
        if self.player:
            self.player.stop()
            self.player.release()
        if self.instance:
            self.instance.release()
        super().closeEvent(event)


def main():
    # High DPI Support
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    
    app = QApplication(sys.argv)
    app.setStyle("Fusion") # Единый вид на всех ОС
    
    player = MediaPlayer()
    player.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
