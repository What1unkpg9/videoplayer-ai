# build.py
# Запуск: python build.py
# Требует: pip install pyinstaller pyqt5 python-vlc
# И установленный в системе VLC (для СБОРКИ, не для запуска результата)

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
    """Находит libvlc, libvlccore и папку plugins в системе."""
    libvlc_path = ctypes.util.find_library('vlc')
    libvlccore_path = ctypes.util.find_library('vlccore')
    
    if not libvlc_path or not libvlccore_path:
        # Фоллбек для Linux/Windows стандартных путей
        if sys.platform == 'win32':
            # Пробуем стандартные папки установки VLC на Windows
            for base in [r"C:\Program Files\VideoLAN\VLC", r"C:\Program Files (x86)\VideoLAN\VLC"]:
                if os.path.exists(os.path.join(base, "libvlc.dll")):
                    libvlc_path = os.path.join(base, "libvlc.dll")
                    libvlccore_path = os.path.join(base, "libvlccore.dll")
                    break
        elif sys.platform == 'darwin':
            # macOS обычно в /usr/local/lib или /opt/homebrew/lib
            pass # ctypes.util обычно находит через dyld
    
    if not libvlc_path or not libvlccore_path:
        print("ERROR: Could not find libvlc / libvlccore via ctypes.util.find_library.")
        print("Install VLC system-wide before building.")
        sys.exit(1)

    libvlc_path = os.path.abspath(libvlc_path)
    libvlccore_path = os.path.abspath(libvlccore_path)
    vlc_root = os.path.dirname(libvlc_path)
    
    # Ищем папку plugins
    # Обычно она рядом с библиотеками или в ../lib/vlc/plugins / ../plugins
    plugin_dir = None
    search_paths = [
        os.path.join(vlc_root, 'plugins'),
        os.path.join(vlc_root, 'vlc', 'plugins'),
        os.path.join(os.path.dirname(vlc_root), 'lib', 'vlc', 'plugins'),
        os.path.join(os.path.dirname(vlc_root), 'vlc', 'plugins'),
    ]
    for p in search_paths:
        if os.path.isdir(p) and any(f.endswith('.dll') or f.endswith('.so') for f in os.listdir(p)):
            plugin_dir = p
            break
    
    if not plugin_dir:
        print("ERROR: Could not find VLC 'plugins' directory.")
        print(f"Searched near: {vlc_root}")
        sys.exit(1)

    print(f"Found VLC:")
    print(f"  libvlc:     {libvlc_path}")
    print(f"  libvlccore: {libvlccore_path}")
    print(f"  plugins:    {plugin_dir}")
    
    return libvlc_path, libvlccore_path, plugin_dir


def main():
    # 1. Находим компоненты VLC
    libvlc, libvlccore, plugin_dir = find_vlc_components()
    
    # 2. Готовим структуру для --add-binary
    # PyInstaller --add-binary "SRC:DEST"
    # DEST — путь ВНУТРИ бинарника (относительно sys._MEIPASS)
    # Мы хотим положить всё в папку 'vlc_libs' внутри бинарника.
    
    binaries = [
        (libvlc, 'vlc_libs'),
        (libvlccore, 'vlc_libs'),
    ]
    
    # Плагины — это дерево папок. PyInstaller понимает формат "SRC:DEST" для папок (рекурсивно).
    # Но безопаснее использовать Tree (Collect all) или просто добавить папку.
    # В PyInstaller API: binaries=[(src, dest)], datas=[(src, dest)].
    # Папку плагинов лучше добавить как datas, чтобы сохранить структуру подпапок (access, demux, video_output...).
    # Но datas не биндингатся в exe на Linux (остаются как файлы рядом), а binaries — встраиваются.
    # Для OneFile на Linux binaries распаковываются в _MEIPASS. datas тоже.
    # Используем datas для папки plugins.
    
    datas = [
        (plugin_dir, 'vlc_libs/plugins'),
    ]

    # 3. Формируем аргументы PyInstaller
    args = [
        ENTRY_POINT,
        f'--name={APP_NAME}',
        '--onefile',
        '--clean',
        f'--distpath={OUTPUT_DIR}',
        f'--workpath={WORK_DIR}',
        '--noconfirm',
        # Скрываем консоль на Windows/macOS (GUI приложение)
        '--noconsole' if sys.platform in ('win32', 'darwin') else '--console',
        # Оптимизация
        '--strip',
        '--noupx', # UPX иногда ломает загруженные плагины VLC
    ]

    # Добавляем бинарники и датас в аргументы
    # PyInstaller CLI не принимает списки напрямую, нужно дублировать флаги
    for src, dest in binaries:
        args.append(f'--add-binary={src}{os.pathsep}{dest}')
    for src, dest in datas:
        args.append(f'--add-data={src}{os.pathsep}{dest}')

    print("\n--- Running PyInstaller ---")
    print(" ".join(args))
    
    # 4. Запуск
    try:
        PyInstaller.__main__.run(args)
    except SystemExit as e:
        if e.code != 0:
            print(f"PyInstaller failed with code {e.code}")
            sys.exit(e.code)
    
    # 5. Проверка результата
    final_exe = Path(OUTPUT_DIR) / (APP_NAME + (".exe" if sys.platform == "win32" else ""))
    if final_exe.exists():
        size_mb = final_exe.stat().st_size / (1024*1024)
        print(f"\n✅ SUCCESS: {final_exe} ({size_mb:.1f} MB)")
        print("Copy this file to a clean machine — it runs without VLC installed.")
    else:
        print("\n❌ Build failed: output not found.")
        sys.exit(1)

if __name__ == "__main__":
    main()
