"""Crea publicaciones de Marketplace moviendo el mouse sobre tu navegador ya
abierto (usa tu sesion tal cual).

Cada carpeta dentro de publicaciones/ es un articulo: sus fotos (.jpg/.png) y
un datos.txt (titulo, precio, categoria, estado) y un descripcion.txt.

Imagenes de botones que usa (en Botones/Crear/):
  titulo, precio, categoria, estado, mas_detalles, agregar_fotos,
  descripcion, etiquetas, siguiente, casilla, publicar
  categorias/<categoria>.png  -> la opcion de la lista de Categoria
  estados/<estado>.png        -> la opcion de la lista de Estado

Uso:
    python publicar_mouse.py                       -> prueba: llena todo y se detiene antes de "Publicar"
    python publicar_mouse.py --confirmar           -> publica de verdad
    python publicar_mouse.py --solo kz-edx-pro-x attack-shark-r1   -> solo esas carpetas

Para detenerlo de emergencia, lleva el mouse a una esquina de la pantalla.
"""
import argparse
import random
import time
from pathlib import Path

import pyautogui
import pyperclip
from PIL import Image, ImageOps

from navegador import preparar_navegador

CARPETA = Path(__file__).resolve().parent
BOTONES = CARPETA / "Botones" / "Crear"
PUBLICACIONES = CARPETA / "publicaciones"
URL_CREAR = "https://www.facebook.com/marketplace/create/item"
PARECIDO = 0.85
MAX_GRUPOS = 20  # limite de Facebook
# Los recortes se hicieron con Windows al 100 %. En otras PCs (laptops al 125 %
# o 150 %) los botones se ven mas grandes: probamos varios tamanos y, cuando uno
# funciona, lo usamos para todo lo demas.
ESCALAS = (1.0, 1.25, 1.5, 1.1, 1.75, 0.9, 2.0)
escala = None

pyautogui.FAILSAFE = True


class FaltaBoton(Exception):
    pass


def pausa(min_seg=0.8, max_seg=1.8):
    time.sleep(random.uniform(min_seg, max_seg))


def leer_datos(carpeta):
    datos = {}
    for linea in (carpeta / "datos.txt").read_text(encoding="utf-8").splitlines():
        if ":" in linea:
            clave, valor = linea.split(":", 1)
            datos[clave.strip().lower()] = valor.strip()
    # La descripcion va en su propio archivo porque tiene varias lineas.
    archivo_descripcion = carpeta / "descripcion.txt"
    if archivo_descripcion.exists():
        datos["descripcion"] = archivo_descripcion.read_text(encoding="utf-8").strip()
    fotos = sorted(p.name for p in carpeta.iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png"))
    return datos, fotos


def buscar(nombre, espera=6, scroll_en=None):
    """Busca el boton en pantalla. Si scroll_en es un punto, baja la pagina ahi
    mientras no lo encuentre. Devuelve su centro o lanza FaltaBoton."""
    ruta = BOTONES / f"{nombre}.png"
    if not ruta.exists():
        # Guardamos como se ve la pantalla para poder recortar el boton que falta.
        captura = CARPETA / f"falta_{nombre.replace('/', '_')}.png"
        pyautogui.screenshot(str(captura))
        raise FaltaBoton(f"Falta la imagen Botones/Crear/{nombre}.png (guarde {captura.name})")
    global escala
    # Abrimos la imagen con Pillow: OpenCV no lee rutas con tildes en Windows.
    original = Image.open(ruta).convert("RGB")
    variantes = []
    for e in ([escala] if escala else ESCALAS):
        recorte = original if e == 1.0 else original.resize(
            (round(original.width * e), round(original.height * e)), Image.LANCZOS)
        # Version invertida en gris: asi un recorte de Facebook en modo oscuro
        # tambien se encuentra en modo claro, y al reves.
        invertido = ImageOps.invert(recorte.convert("L")).convert("RGB")
        variantes += [(recorte, False, e), (invertido, True, e)]
    inicio = time.time()
    while time.time() - inicio < espera:
        punto = None
        for imagen, gris, e in variantes:
            try:
                punto = pyautogui.locateCenterOnScreen(imagen, confidence=PARECIDO, grayscale=gris)
            except pyautogui.ImageNotFoundException:
                punto = None
            if punto:
                if escala is None and e != 1.0:
                    print(f"   (tu pantalla esta al {e:.0%}, ajusto los tamanos)")
                escala = e
                return punto
        if scroll_en:
            pyautogui.moveTo(scroll_en)
            pyautogui.scroll(-200)
            time.sleep(0.6)
        else:
            time.sleep(0.3)
    raise FaltaBoton(f"No encontre '{nombre}' en pantalla")


def clic(nombre, **kwargs):
    punto = buscar(nombre, **kwargs)
    pyautogui.moveTo(punto, duration=random.uniform(0.2, 0.5))
    pyautogui.click()
    pausa()
    return punto


def pegar(texto):
    """Pega texto con el portapapeles (asi no fallan tildes ni simbolos)."""
    pyperclip.copy(texto)
    pyautogui.hotkey("ctrl", "v")
    pausa(0.4, 0.8)


def ir_a(url):
    pyautogui.hotkey("ctrl", "l")
    time.sleep(0.4)
    pegar(url)
    pyautogui.press("enter")
    pausa(4, 6)


def subir_fotos(carpeta, fotos):
    clic("agregar_fotos", espera=15)
    time.sleep(2)  # que abra la ventana "Abrir" de Windows
    pegar(str(carpeta))
    pyautogui.press("enter")
    time.sleep(1.5)
    pegar(" ".join(f'"{f}"' for f in fotos))
    pyautogui.press("enter")
    time.sleep(3 + 2 * len(fotos))  # tiempo para que suban


def elegir_opcion(campo, subcarpeta, valor, formulario):
    campo_abierto = clic(campo, scroll_en=formulario)
    # Facebook abre la lista debajo del campo, o encima si el campo esta en la
    # mitad de abajo de la pantalla. Si la opcion no se ve, bajamos dentro de la lista.
    if campo_abierto.y > pyautogui.size().height / 2:
        lista = pyautogui.Point(campo_abierto.x, campo_abierto.y - 150 * (escala or 1))
    else:
        lista = pyautogui.Point(campo_abierto.x, campo_abierto.y + 150 * (escala or 1))
    clic(f"{subcarpeta}/{valor}", espera=12, scroll_en=lista)


def marcar_grupos(lista):
    casilla = Image.open(BOTONES / "casilla.png").convert("RGB")
    if escala and escala != 1.0:
        casilla = casilla.resize((round(casilla.width * escala), round(casilla.height * escala)), Image.LANCZOS)
    # La casilla se recorto en modo oscuro; invertida sirve para modo claro.
    variantes = ((casilla, False), (ImageOps.invert(casilla.convert("L")).convert("RGB"), True))
    marcados = 0
    sin_nuevos = 0
    while marcados < MAX_GRUPOS and sin_nuevos < 2:
        casillas = []
        for imagen, gris in variantes:
            try:
                casillas += list(pyautogui.locateAllOnScreen(imagen, confidence=0.9, grayscale=gris))
            except Exception as e:  # noqa: BLE001 - "no encontre ninguna" no es un error
                if "ImageNotFound" not in type(e).__name__:
                    raise
        if not casillas:
            sin_nuevos += 1
        else:
            sin_nuevos = 0
        usados = []
        for caja in casillas:
            centro = pyautogui.center(caja)
            if any(abs(centro.x - u.x) < 10 and abs(centro.y - u.y) < 10 for u in usados):
                continue
            usados.append(centro)
            pyautogui.moveTo(centro, duration=0.2)
            pyautogui.click()
            marcados += 1
            time.sleep(0.4)
            if marcados >= MAX_GRUPOS:
                break
        pyautogui.moveTo(lista)
        pyautogui.scroll(-300)
        time.sleep(0.8)
    print(f"   Grupos marcados: {marcados}")


def publicar(carpeta, confirmar):
    datos, fotos = leer_datos(carpeta)
    print(f"Articulo: {datos.get('titulo', carpeta.name)} ({len(fotos)} fotos)")

    ir_a(URL_CREAR)
    titulo = buscar("titulo", espera=20)  # tambien espera a que cargue
    formulario = pyautogui.Point(titulo.x, titulo.y)

    subir_fotos(carpeta, fotos)

    clic("titulo", scroll_en=formulario)
    pegar(datos["titulo"])
    clic("precio", scroll_en=formulario)
    pegar(datos["precio"])
    elegir_opcion("categoria", "categorias", datos["categoria"], formulario)
    elegir_opcion("estado", "estados", datos["estado"], formulario)

    if datos.get("descripcion"):
        # "Mas detalles" a veces ya viene abierta y a veces no. Primero buscamos
        # Descripcion bajando la pagina; si no aparece, subimos un poco, abrimos
        # "Mas detalles" y volvemos a buscar.
        for intento in range(3):
            try:
                clic("descripcion", espera=4, scroll_en=formulario)
                break
            except FaltaBoton:
                if intento == 2:
                    raise
                pyautogui.moveTo(formulario)
                pyautogui.scroll(2000)  # volver arriba del formulario
                time.sleep(0.8)
                clic("mas_detalles", scroll_en=formulario)
        pegar(datos["descripcion"])
    if datos.get("etiquetas"):
        clic("etiquetas", scroll_en=formulario)
        for etiqueta in datos["etiquetas"].split(","):
            if etiqueta.strip():
                pegar(etiqueta.strip())
                pyautogui.press("enter")
                time.sleep(0.4)

    clic("siguiente", espera=15, scroll_en=formulario)
    pausa(2, 3)
    marcar_grupos(formulario)

    if not confirmar:
        boton = buscar("publicar", espera=10)
        pyautogui.moveTo(boton, duration=0.4)
        print("   MODO PRUEBA: aqui le daria clic a 'Publicar'. No publique nada.")
        print("   Para publicar de verdad: python publicar_mouse.py --confirmar")
        return
    # Si el boton sigue en pantalla despues del clic, no se publico: reintentamos.
    for intento in range(3):
        clic("publicar", espera=10)
        pausa(5, 8)
        try:
            buscar("publicar", espera=1)
        except FaltaBoton:
            print("   Publicado.")
            return
        print(f"   'Publicar' sigue en pantalla, intento {intento + 2}...")
    pyautogui.screenshot(str(CARPETA / "error_publicar.png"))
    raise FaltaBoton("Di clic en 'Publicar' 3 veces y no se publico")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirmar", action="store_true", help="publica de verdad")
    parser.add_argument("--solo", nargs="+", help="nombres de carpetas de publicaciones/")
    args = parser.parse_args()

    carpetas = sorted(p for p in PUBLICACIONES.iterdir() if (p / "datos.txt").exists())
    if args.solo:
        carpetas = [p for p in carpetas if p.name in args.solo]
    if not carpetas:
        raise SystemExit("No hay articulos en publicaciones/ (cada uno necesita su datos.txt).")

    preparar_navegador(URL_CREAR)
    for carpeta in carpetas:
        try:
            publicar(carpeta, args.confirmar)
        except FaltaBoton as e:
            print(f"   {e}. Me detengo y guardo error_publicar.png")
            pyautogui.screenshot("error_publicar.png")
            break
        pausa(5, 10)


if __name__ == "__main__":
    main()
