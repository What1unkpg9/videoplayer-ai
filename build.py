# build.py
import sys
import os
import shutil
import subprocess
import ctypes.util
from pathlib import Path

try:
    import PyInstaller.__main__
except ImportError:
    print("PyInstaller not installed. Run: pip install pyinstaller")
    sys.exit(1)

APP_NAME = "VLC_Portable_Player"
ENTRY_POINT = "main.py"
OUTPUT_DIR = "dist_portable"
WORK_DIR = "build_portable"

def find_vlc_components():
    """
    Находит libvlc, libvlccore и папку plugins.
    Приоритет: системный поиск (ctypes) -> хардкод путей для GH Actions -> стандартные системные пути.
    """
    libvlc_path = ctypes.util.find_library('vlc')
    libvlccore_path = ctypes.util.find_library('vlccore')
    plugin_dir = None

    # --- 1. Определяем корневую папку VLC (vlc_root) ---
    vlc_root = None
    if libvlc_path:
        vlc_root = os.path.dirname(os.path.abspath(libvlc_path))

    # Фоллбеки для GH Actions / специфичных ОС, если ctypes не нашел
    if not vlc_root:
        if sys.platform == 'linux':
            # Ubuntu GH Actions: библиотеки в /usr/lib/x86_64-linux-gnu/, плагины рядом
            vlc_root = "/usr/lib/x86_64-linux-gnu"
        elif sys.platform == 'darwin':
            # macOS GH Actions (brew install vlc): симлинки в /usr/local/opt/vlc/lib, но реальные либы и плагины в .app
            # Приоритет: .app bundle (содержит плагины), потом keg-only prefix
            if os.path.isdir("/Applications/VLC.app/Contents/MacOS/lib"):
                vlc_root = "/Applications/VLC.app/Contents/MacOS/lib"
            elif os.path.isdir("/usr/local/opt/vlc/lib"):
                vlc_root = "/usr/local/opt/vlc/lib"
            elif os.path.isdir("/opt/homebrew/opt/vlc/lib"):
                vlc_root = "/opt/homebrew/opt/vlc/lib"
        elif sys.platform == 'win32':
            for base in [r"C:\Program Files\VideoLAN\VLC", r"C:\Program Files (x86)\VideoLAN\VLC"]:
                if os.path.exists(os.path.join(base, "libvlc.dll")):
                    vlc_root = base
                    break

    # Если нашли vlc_root, пробуем уточнить пути к либам
    if vlc_root and not libvlc_path:
        if sys.platform == 'win32':
            libvlc_path = os.path.join(vlc_root, "libvlc.dll")
            libvlccore_path = os.path.join(vlc_root, "libvlccore.dll")
        elif sys.platform == 'darwin':
            libvlc_path = os.path.join(vlc_root, "libvlc.dylib")
            libvlccore_path = os.path.join(vlc_root, "libvlccore.dylib")
        else: # linux
            libvlc_path = os.path.join(vlc_root, "libvlc.so")
            libvlccore_path = os.path.join(vlc_root, "libvlccore.so")

    # Финальная проверка существования либ
    if not libvlc_path or not os.path.exists(libvlc_path):
        print(f"ERROR: libvlc not found. Searched: {libvlc_path}")
        sys.exit(1)
    if not libvlccore_path or not os.path.exists(libvlccore_path):
        print(f"ERROR: libvlccore not found. Searched: {libvlccore_path}")
        sys.exit(1)

    libvlc_path = os.path.abspath(libvlc_path)
    libvlccore_path = os.path.abspath(libvlccore_path)
    # vlc_root обновляем на основе реально найденной либы
    vlc_root = os.path.dirname(libvlc_path)

    # --- 2. Поиск папки plugins (КРИТИЧЕСКИ ВАЖНО) ---
    # Порядок важен: сначала специфичные для GH Actions пути, потом общие
    search_paths = []
    
    if sys.platform == 'linux':
        # Ubuntu 22.04/24.04 на GH Actions
        search_paths.append("/usr/lib/x86_64-linux-gnu/vlc/plugins")
        # Общие пути
        search_paths.append(os.path.join(vlc_root, "vlc", "plugins"))
        search_paths.append(os.path.join(vlc_root, "plugins"))
    elif sys.platform == 'darwin':
        # macOS: внутри .app бандла (гарантированно есть после brew install vlc --cask или ручной установки)
        # brew install vlc (formula) не ставит .app, но ставит плагины в keg.
        # На GH Actions `brew install vlc` ставит формулу. Плагины в /usr/local/opt/vlc/lib/vlc/plugins
        search_paths.append(os.path.join(vlc_root, "vlc", "plugins")) # Для .app/Contents/MacOS/lib/vlc/plugins или keg/lib/vlc/plugins
        search_paths.append("/Applications/VLC.app/Contents/MacOS/lib/vlc/plugins") # На случай, если vlc_root было другое
        search_paths.append("/usr/local/opt/vlc/lib/vlc/plugins")
        search_paths.append("/opt/homebrew/opt/vlc/lib/vlc/plugins")
    elif sys.platform == 'win32':
        search_paths.append(os.path.join(vlc_root, "plugins"))
    
    # Добавляем стандартные относительные пути на всякий случай
    search_paths.extend([
        os.path.join(vlc_root, "vlc", "plugins"),
        os.path.join(vlc_root, "plugins"),
        os.path.join(os.path.dirname(vlc_root), "lib", "vlc", "plugins"),
        os.path.join(os.path.dirname(vlc_root), "vlc", "plugins"),
    ])

    for p in search_paths:
        p_abs = os.path.abspath(p)
        # Проверяем наличие хотя бы одного файла плагина (.so, .dll, .dylib)
        if os.path.isdir(p_abs):
            try:
                if any(f.endswith(('.so', '.dll', '.dylib')) for f in os.listdir(p_abs)):
                    plugin_dir = p_abs
                    break
            except OSError:
                continue

    if not plugin_dir:
        print("ERROR: Could not find VLC 'plugins' directory.")
        print(f"Searched in:")
        for p in search_paths: print(f"  - {p}")
        sys.exit(1)

    print(f"Found VLC Components:")
    print(f"  libvlc:     {libvlc_path}")
    print(f"  libvlccore: {libvlccore_path}")
    print(f"  plugins:    {plugin_dir}")
    
    return libvlc_path, libvlccore_path, plugin_dir


def main():
    # 1. Находим компоненты
    libvlc, libvlccore, plugin_dir = find_vlc_components()
    
    # 2. Подготавливаем аргументы для PyInstaller
    # --add-binary "SRC:DEST" -> DEST относится к sys._MEIPASS
    # Кладем всё в vlc_libs/ внутри бинарника
    binaries = [
        (libvlc, 'vlc_libs'),
        (libvlccore, 'vlc_libs'),
    ]
    
    # Плагины — папку. Используем --add-data для сохранения структуры подкаталогов (access, demux, ...)
    # На Linux/macOS в onefile datas тоже распаковываются в _MEIPASS.
    datas = [
        (plugin_dir, 'vlc_libs/plugins'),
    ]

    # 3. Аргументы PyInstaller
    args = [
        ENTRY_POINT,
        f'--name={APP_NAME}',
        '--onefile',
        '--clean',
        f'--distpath={OUTPUT_DIR}',
        f'--workpath={WORK_DIR}',
        '--noconfirm',
        # GUI режим (нет консоли) на Win/macOS, на Linux консоль нужна для логов/отладки
        '--noconsole' if sys.platform in ('win32', 'darwin') else '--console',
        '--strip',
        '--noupx', # UPX часто ломает плагины VLC (сжатие .so/.dll внутри)
    ]

    # Добавляем бинарники и данные
    # os.pathsep это ';' на Windows, ':' на Unix. PyInstaller CLI ожидает этот разделитель.
    sep = os.pathsep
    for src, dest in binaries:
        args.append(f'--add-binary={src}{sep}{dest}')
    for src, dest in datas:
        args.append(f'--add-data={src}{sep}{dest}')

    print("\n--- Running PyInstaller ---")
    # print(" ".join(args)) # Для отладки командной строки
    
    try:
        PyInstaller.__main__.run(args)
    except SystemExit as e:
        if e.code != 0:
            print(f"PyInstaller failed with code {e.code}")
            sys.exit(e.code)
    
    # 4. Верификация артефакта
    final_name = APP_NAME + (".exe" if sys.platform == "win32" else "")
    final_exe = Path(OUTPUT_DIR) / final_name
    
    if final_exe.exists():
        size_mb = final_exe.stat().st_size / (1024 * 1024)
        print(f"\n✅ SUCCESS: {final_exe} ({size_mb:.1f} MB)")
        print("Portable binary ready. Upload artifact from 'dist_portable'.")
    else:
        print(f"\n❌ Build failed: Output not found at {final_exe}")
        sys.exit(1)

if __name__ == "__main__":
    main()
