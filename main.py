# -*- coding: utf-8 -*-
"""
ContabilidadAPP - Lanzador de Escritorio

Inicia el servidor Django local en un puerto libre y lo muestra
en una ventana nativa usando pywebview. Al cerrar la ventana,
se detiene el servidor automáticamente.

Uso:
    python main.py
"""
import os
import socket
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
os.chdir(BASE_DIR)

LOG_FILE = BASE_DIR / 'app.log'


def log(msg):
    """Registra el mensaje en consola y en app.log."""
    line = f'[{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}] {msg}'
    try:
        print(line)
    except Exception:
        pass
    try:
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    except OSError:
        pass


def alert(msg):
    """Muestra un mensaje de error al usuario (ventana o consola)."""
    log(msg)
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, msg, 'ContabilidadAPP', 0x10)
    except Exception:
        try:
            input(msg + '\n\nPresione Enter para salir...')
        except EOFError:
            pass


def find_free_port():
    """Busca un puerto libre en la máquina."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def run_migrations():
    """Ejecuta las migraciones pendientes de Django."""
    log('Aplicando migraciones de la base de datos...')
    result = subprocess.run(
        [sys.executable, 'manage.py', 'migrate', '--no-input'],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        log('Error en migraciones:\n' + result.stderr)
        raise RuntimeError('No se pudieron aplicar las migraciones de la base de datos.')
    log('Migraciones completadas.')


def start_server(port):
    """Inicia el servidor Django en segundo plano."""
    env = os.environ.copy()
    env['DJANGO_SETTINGS_MODULE'] = 'config.settings'
    proc = subprocess.Popen(
        [sys.executable, 'manage.py', 'runserver', f'127.0.0.1:{port}', '--noreload'],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=env,
    )
    return proc


def wait_for_server(port, timeout=30):
    """Espera a que el servidor responda."""
    url = f'http://127.0.0.1:{port}/'
    log(f'Esperando servidor en {url} ...')
    start = time.time()
    while time.time() - start < timeout:
        try:
            urllib.request.urlopen(url, timeout=2)
            log('Servidor listo.')
            return True
        except Exception:
            time.sleep(0.4)
    return False


def open_window(url, port):
    """Abre la ventana nativa con pywebview; si falla, abre el navegador."""
    try:
        import webview
    except ImportError:
        log('pywebview no disponible. Abriendo en el navegador por defecto...')
        import webbrowser
        webbrowser.open(url)
        return

    webview.create_window(
        'ContabilidadAPP',
        url,
        width=1280,
        height=820,
        resizable=True,
        min_size=(900, 600),
        background_color='#FFFFFF',
    )
    log('Ventana abierta. Esperando que el usuario la cierre...')
    webview.start()
    log('Ventana cerrada.')


def main():
    port = find_free_port()
    url = f'http://127.0.0.1:{port}/'

    try:
        run_migrations()
    except RuntimeError as exc:
        alert(str(exc))
        return 1

    server = start_server(port)
    log(f'Servidor iniciado en http://127.0.0.1:{port}/')

    try:
        if not wait_for_server(port):
            raise RuntimeError('El servidor no arrancó a tiempo. Revise app.log.')
        open_window(url, port)
    except Exception as exc:
        alert(f'Error inesperado: {exc}')
        return 1
    finally:
        log('Deteniendo servidor...')
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()

    log('Aplicación cerrada correctamente.')
    return 0


if __name__ == '__main__':
    sys.exit(main())