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


def traer_navegador():
    """Busca la ventana de Facebook (o, si no, cualquier navegador) y la activa.

    Devuelve True si la puso al frente.
    """
    ventanas = _ventanas()
    candidatas = [v for v in ventanas if "Facebook" in _titulo(v) and any(n in _titulo(v) for n in NAVEGADORES)]
    candidatas = candidatas or [v for v in ventanas if any(n in _titulo(v) for n in NAVEGADORES)]
    if not candidatas:
        return False
    ventana = candidatas[0]
    print(f"Pongo al frente: {_titulo(ventana)}")
    try:
        if ventana.isMinimized:
            ventana.restore()
        ventana.activate()
    except Exception:  # noqa: BLE001 - Windows a veces no deja activar; este truco si funciona
        try:
            ventana.minimize()
            ventana.restore()
        except Exception:  # noqa: BLE001
            return False
    try:
        if not ventana.isMaximized:
            ventana.maximize()
    except Exception:  # noqa: BLE001
        pass
    time.sleep(1.5)
    return True


def preparar_navegador():
    if traer_navegador():
        return
    print("No encontre tu navegador abierto. Abre Facebook en Chrome, Brave o Edge.")
    print("Tienes 8 segundos para ponerlo al frente...")
    time.sleep(8)
