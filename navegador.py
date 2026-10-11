"""Pone al frente la ventana del navegador con Facebook antes de que el bot empiece."""
import time

NAVEGADORES = ("Google Chrome", "Brave", "Microsoft Edge", "Opera", "Firefox")


def _ventanas():
    try:
        import pygetwindow as gw  # viene con pyautogui en Windows
    except ImportError:
        return []
    return [v for v in gw.getAllWindows() if v.title.strip()]


def _titulo(ventana):
    # Edge escribe "Microsoft\u200b Edge" con un espacio invisible en el titulo.
    return ventana.title.replace("\u200b", "").strip()


def _al_frente(hwnd):
    """Pone la ventana al frente. Windows bloquea esto si lo pide un programa que
    no esta al frente, asi que usamos los trucos de siempre: simular la tecla Alt
    y "engancharnos" a la ventana que si esta al frente."""
    import ctypes

    import pyautogui

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    pyautogui.press("alt")
    actual = user32.GetForegroundWindow()
    hilo_actual = user32.GetWindowThreadProcessId(actual, None)
    mi_hilo = kernel32.GetCurrentThreadId()
    user32.AttachThreadInput(hilo_actual, mi_hilo, True)
    try:
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
    finally:
        user32.AttachThreadInput(hilo_actual, mi_hilo, False)
    user32.ShowWindow(hwnd, 3)  # SW_MAXIMIZE
    time.sleep(0.8)
    return user32.GetForegroundWindow() == hwnd


def traer_navegador():
    """Busca la ventana de Facebook (o, si no, cualquier navegador) y la pone al frente.

    Devuelve True si lo logro.
    """
    ventanas = _ventanas()
    candidatas = [v for v in ventanas if "Facebook" in _titulo(v) and any(n in _titulo(v) for n in NAVEGADORES)]
    candidatas = candidatas or [v for v in ventanas if any(n in _titulo(v) for n in NAVEGADORES)]
    if not candidatas:
        print("Ventanas abiertas que vi:")
        for v in ventanas[:15]:
            print(f"   - {_titulo(v)}")
        return False
    ventana = candidatas[0]
    print(f"Pongo al frente: {_titulo(ventana)}")
    for _ in range(3):
        try:
            if _al_frente(ventana._hWnd):
                time.sleep(1)
                return True
        except Exception as e:  # noqa: BLE001 - seguimos intentando
            print(f"   (no pude: {e})")
        time.sleep(0.5)
    print("   Windows no me dejo poner el navegador al frente.")
    return False


def preparar_navegador(url):
    """Deja Facebook al frente. Si Windows no deja traer la ventana, abre la
    pagina con el navegador predeterminado: asi Windows si lo pone al frente."""
    if traer_navegador():
        return
    import webbrowser

    print("Abro Facebook en tu navegador predeterminado...")
    webbrowser.open(url)
    time.sleep(7)
