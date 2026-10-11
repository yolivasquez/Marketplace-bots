"""Borra tus publicaciones de Marketplace moviendo el mouse sobre tu navegador
ya abierto (usa tu sesion tal cual).

Proceso por cada publicacion:
  1. Busca el boton "Compartir" de la primera publicacion (botones/compartir.png)
     y el "..." a su derecha (botones/opciones.png).
  2. Le da clic y, solo alrededor de ese boton, busca "Eliminar publicacion"
     (botones/eliminar.png).
  3. En el centro de la pantalla busca el boton azul "Eliminar" de la
     confirmacion (botones/confirmar.png).
  4. Espera, recarga la pagina y repite.

Uso:
    python borrar_mouse.py              -> prueba: hace los pasos 1 y 2, cierra el menu con Esc y no borra nada
    python borrar_mouse.py --confirmar  -> borra de verdad
    python borrar_mouse.py --confirmar --max 5

Para detenerlo de emergencia, lleva el mouse a una esquina de la pantalla.
"""
import argparse
import random
import time
from pathlib import Path

import pyautogui
from PIL import Image, ImageOps

from navegador import preparar_navegador

BOTONES = Path(__file__).resolve().parent / "botones"
URL_VENTAS = "https://www.facebook.com/marketplace/you/selling"
PARECIDO = 0.85  # que tanto debe parecerse la pantalla al recorte (0 a 1)
# Los recortes se hicieron con Windows al 100 %. En otras PCs (laptops al 125 %
# o 150 %) los botones se ven mas grandes: probamos varios tamanos y, cuando uno
# funciona, lo usamos para todo lo demas.
ESCALAS = (1.0, 1.25, 1.5, 1.1, 1.75, 0.9, 2.0)
escala = None

pyautogui.FAILSAFE = True  # mouse en una esquina = detener


def pausa(min_seg=1.0, max_seg=2.5):
    time.sleep(random.uniform(min_seg, max_seg))


def recortar_a_pantalla(izq, arriba, ancho, alto):
    """Ajusta una zona de busqueda para que no se salga de la pantalla."""
    pantalla_w, pantalla_h = pyautogui.size()
    izq, arriba = max(0, izq), max(0, arriba)
    ancho = min(ancho, pantalla_w - izq)
    alto = min(alto, pantalla_h - arriba)
    return (int(izq), int(arriba), int(ancho), int(alto))


def zona_centro():
    """La parte central de la pantalla, donde Facebook abre la confirmacion."""
    w, h = pyautogui.size()
    return recortar_a_pantalla(w // 4, h // 6, w // 2, h * 2 // 3)


def px(valor):
    """Convierte una distancia medida al 100 % a la escala de esta pantalla."""
    return valor * (escala or 1.0)


def zona_alrededor(punto):
    """Zona alrededor del boton "..." donde se abre su menu."""
    return recortar_a_pantalla(punto.x - px(450), punto.y - px(450), px(700), px(900))


def buscar(nombre, zona=None, espera=6, caja=False):
    """Espera hasta `espera` segundos a que aparezca el boton.

    Devuelve su centro (o su caja completa si caja=True), o None.
    """
    global escala
    # nombre.png es el boton en espanol; nombre_en.png (u otros nombre_*.png)
    # son el mismo boton con Facebook en otro idioma.
    archivos = [BOTONES / f"{nombre}.png", *sorted(BOTONES.glob(f"{nombre}_*.png"))]
    variantes = []
    for archivo in archivos:
        if not archivo.exists():
            continue
        original = Image.open(archivo).convert("RGB")
        for e in ([escala] if escala else ESCALAS):
            recorte = original if e == 1.0 else original.resize(
                (round(original.width * e), round(original.height * e)), Image.LANCZOS)
            # Version invertida en gris: asi los recortes de Facebook en modo oscuro
            # tambien sirven en modo claro (y en otro navegador con otro tema).
            invertido = ImageOps.invert(recorte.convert("L")).convert("RGB")
            variantes += [(recorte, False, e), (invertido, True, e)]
    inicio = time.time()
    while time.time() - inicio < espera:
        encontrado = None
        for imagen, gris, e in variantes:
            try:
                encontrado = pyautogui.locateOnScreen(imagen, confidence=PARECIDO, region=zona, grayscale=gris)
            except (pyautogui.ImageNotFoundException, ValueError):  # ValueError: recorte mas grande que la zona
                encontrado = None
            if encontrado:
                if escala is None and e != 1.0:
                    print(f"   (tu pantalla esta al {e:.0%}, ajusto los tamanos)")
                escala = e
                break
        if encontrado:
            print(f"   {nombre}: encontrado en {time.time() - inicio:.1f} s")
            return encontrado if caja else pyautogui.center(encontrado)
        time.sleep(0.3)
    print(f"   {nombre}: no lo encontre en {espera} s")
    return None


def guardar_error(punto=None, zona=None):
    """Guarda error_borrar.png marcando en rojo donde dio clic y donde busco."""
    from PIL import ImageDraw

    imagen = pyautogui.screenshot()
    dibujo = ImageDraw.Draw(imagen)
    if zona:
        izq, arriba, ancho, alto = zona
        dibujo.rectangle([izq, arriba, izq + ancho, arriba + alto], outline="red", width=4)
    if punto:
        dibujo.ellipse([punto.x - 20, punto.y - 20, punto.x + 20, punto.y + 20], outline="red", width=4)
    imagen.save(Path(__file__).resolve().parent / "error_borrar.png")
    print("   Guarde error_borrar.png: circulo = donde di clic, cuadro = donde busque.")


def clic(punto):
    pyautogui.moveTo(punto, duration=random.uniform(0.2, 0.5))
    pyautogui.click()


def abrir_ventas():
    pyautogui.hotkey("ctrl", "l")
    time.sleep(0.5)
    pyautogui.write(URL_VENTAS, interval=0.02)
    pyautogui.press("enter")
    pausa(4, 6)


def borrar_una(confirmar):
    """Hace el proceso con la primera publicacion. Devuelve True si salio bien."""
    # El "..." se parece a muchas zonas grises, asi que primero buscamos el
    # boton "Compartir" (que si es unico) y luego el "..." a su derecha o debajo.
    # Esto tambien espera a que la pagina termine de cargar.
    compartir = buscar("compartir", espera=15, caja=True)
    if not compartir:
        guardar_error()
        return False
    a_la_derecha = recortar_a_pantalla(compartir.left + compartir.width, compartir.top - px(15),
                                       px(120), compartir.height + px(30))
    puntos = buscar("opciones", zona=a_la_derecha, espera=2)
    if not puntos:
        # En publicaciones viejas aparece "Volver a publicar este articulo" y
        # el "..." baja a la siguiente linea, a la izquierda.
        abajo = recortar_a_pantalla(compartir.left - px(700), compartir.top + compartir.height - px(5),
                                    px(700) + compartir.width + px(120), px(80))
        puntos = buscar("opciones", zona=abajo, espera=2)
    if not puntos:
        guardar_error(zona=abajo)
        return False
    clic(puntos)

    zona = zona_alrededor(puntos)
    eliminar = buscar("eliminar", zona=zona, espera=10)
    if not eliminar:
        guardar_error(puntos, zona)
        pyautogui.press("esc")
        return False
    if not confirmar:
        pyautogui.moveTo(eliminar, duration=0.4)
        print("   Prueba: aqui le daria clic a 'Eliminar publicacion'. Cierro el menu.")
        time.sleep(1.5)
        pyautogui.press("esc")
        return True
    clic(eliminar)

    boton_final = buscar("confirmar", zona=zona_centro(), espera=20)  # a veces Facebook tarda en abrirlo
    if not boton_final:
        guardar_error(eliminar, zona_centro())
        pyautogui.press("esc")
        return False
    clic(boton_final)
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirmar", action="store_true", help="borra de verdad")
    parser.add_argument("--max", type=int, default=20, help="maximo a borrar por corrida")
    args = parser.parse_args()

    for necesario in ("compartir", "opciones", "eliminar", "confirmar"):
        if not (BOTONES / f"{necesario}.png").exists():
            raise SystemExit(f"Falta botones/{necesario}.png (ver README).")

    preparar_navegador(URL_VENTAS)
    abrir_ventas()

    if not args.confirmar:
        print("Modo prueba (no borra nada):")
        ok = borrar_una(confirmar=False)
        print("La prueba salio bien." if ok else "La prueba fallo; mandame lo de arriba.")
        return

    borradas = 0
    while borradas < args.max:
        print(f"Publicacion {borradas + 1}:")
        if not borrar_una(confirmar=True):
            if borradas:
                print("Ya no encontre mas publicaciones (o algo no aparecio); me detengo.")
            else:
                print("Algo no aparecio; me detengo.")
            break
        borradas += 1
        print(f"   Borrada. Total: {borradas}")
        pausa(3, 5)
        pyautogui.press("f5")
        pausa(4, 6)

    print(f"Termine. Publicaciones borradas: {borradas}")


if __name__ == "__main__":
    main()
