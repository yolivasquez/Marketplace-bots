"""Ventana del Marketplace bot.

- Lista de plantillas (carpetas en publicaciones/) con casilla "Publicar".
- Crear, editar, duplicar y borrar plantillas, con sus fotos.
- Vista previa de las fotos y la descripcion.
- Botones para probar, publicar y borrar publicaciones con los bots.

Lo que marcas para publicar se guarda en esta PC (no en la carpeta
compartida), asi cada persona elige lo suyo.
"""
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import threading
import tkinter as tk
import traceback
import unicodedata
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageOps, ImageTk

try:  # fotos HEIC del iPhone
    import pillow_heif

    pillow_heif.register_heif_opener()
except ImportError:
    pass

try:  # tema moderno (estilo Windows 11)
    import sv_ttk
except ImportError:
    sv_ttk = None

CARPETA = Path(__file__).resolve().parent
PUBLICACIONES = CARPETA / "publicaciones"
CATEGORIAS = CARPETA / "Botones" / "Crear" / "categorias"
ESTADOS = CARPETA / "Botones" / "Crear" / "estados"
HISTORIAL = CARPETA / "historial.csv"
LOCAL = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "MarketplaceBot"
SELECCION = LOCAL / "seleccion.json"
FOTOS_OK = (".jpg", ".jpeg", ".png")
FOTOS_TODAS = FOTOS_OK + (".heic", ".heif")

ESTADOS_FB = ["Nuevo", "Usado - Como nuevo", "Usado - Buen estado", "Usado - Aceptable"]

# Colores para los widgets que el tema no pinta (cuadros de texto y listas).
FONDO_TEXTO = "#1f1f1f" if sv_ttk else "white"
LETRA_TEXTO = "#e8e8e8" if sv_ttk else "black"
ACENTO = "#57c8ff"
FUENTE = "Segoe UI"


# ---------- plantillas en disco ----------

def leer_plantilla(carpeta):
    datos = {}
    archivo = carpeta / "datos.txt"
    if archivo.exists():
        for linea in archivo.read_text(encoding="utf-8").splitlines():
            if ":" in linea:
                clave, valor = linea.split(":", 1)
                datos[clave.strip().lower()] = valor.strip()
    descripcion = carpeta / "descripcion.txt"
    datos["descripcion"] = descripcion.read_text(encoding="utf-8").strip() if descripcion.exists() else ""
    datos["fotos"] = sorted(p for p in carpeta.iterdir() if p.suffix.lower() in FOTOS_OK)
    return datos


def listar_plantillas():
    if not PUBLICACIONES.exists():
        return []
    return sorted(p for p in PUBLICACIONES.iterdir() if (p / "datos.txt").exists())


def nombre_carpeta(titulo):
    texto = unicodedata.normalize("NFKD", titulo).encode("ascii", "ignore").decode()
    texto = re.sub(r"[^a-zA-Z0-9]+", "-", texto).strip("-").lower()[:40] or "articulo"
    nombre, n = texto, 2
    while (PUBLICACIONES / nombre).exists():
        nombre, n = f"{texto}-{n}", n + 1
    return nombre


def a_jpg(origen, destino):
    """Copia una foto; si es HEIC (iPhone) la convierte a JPG."""
    if origen.suffix.lower() in (".heic", ".heif"):
        imagen = ImageOps.exif_transpose(Image.open(origen)).convert("RGB")
        imagen.save(destino.with_suffix(".jpg"), quality=92)
        return destino.with_suffix(".jpg")
    destino = destino.with_suffix(origen.suffix.lower())
    shutil.copy2(origen, destino)
    return destino


def guardar_plantilla(carpeta, datos, fotos):
    """Guarda datos, descripcion y fotos en orden (01, 02, ...; la 01 es la portada)."""
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / "datos.txt").write_text(
        f"titulo: {datos['titulo']}\nprecio: {datos['precio']}\n"
        f"categoria: {datos['categoria']}\nestado: {datos['estado']}\n",
        encoding="utf-8",
    )
    (carpeta / "descripcion.txt").write_text(datos["descripcion"].strip() + "\n", encoding="utf-8")

    # Primero todo a una carpeta temporal y luego se renombra en orden.
    temporal = carpeta / "_nuevas"
    temporal.mkdir(exist_ok=True)
    nuevas = [a_jpg(Path(f), temporal / f"{i:02d}") for i, f in enumerate(fotos, 1)]
    for vieja in carpeta.iterdir():
        if vieja.is_file() and vieja.suffix.lower() in FOTOS_TODAS:
            quitar_solo_lectura(vieja)
            vieja.unlink()
    for foto in nuevas:
        foto.replace(carpeta / foto.name)
    temporal.rmdir()


def quitar_solo_lectura(ruta):
    try:
        os.chmod(ruta, stat.S_IWRITE | stat.S_IREAD)
    except OSError:
        pass


def borrar_carpeta(carpeta):
    """Borra la carpeta aunque Windows o Drive hayan dejado archivos de solo lectura."""
    def reintentar(funcion, ruta, *_):
        quitar_solo_lectura(ruta)
        funcion(ruta)

    if sys.version_info >= (3, 12):
        shutil.rmtree(carpeta, onexc=reintentar)
    else:
        shutil.rmtree(carpeta, onerror=reintentar)


# ---------- fotos en miniatura ----------

_cache_fotos = {}


def foto_tk(ruta, ancho, alto, recortar=False):
    """Devuelve la foto lista para mostrar en la ventana (con cache)."""
    ruta = Path(ruta)
    try:
        clave = (str(ruta), ruta.stat().st_mtime, ancho, alto, recortar)
    except OSError:
        return None
    if clave not in _cache_fotos:
        try:
            with Image.open(ruta) as imagen:
                imagen.draft("RGB", (ancho * 2, alto * 2))  # mas rapido con fotos grandes
                imagen = ImageOps.exif_transpose(imagen).convert("RGB")
                if recortar:
                    imagen = ImageOps.fit(imagen, (ancho, alto))
                else:
                    imagen.thumbnail((ancho, alto))
                _cache_fotos[clave] = ImageTk.PhotoImage(imagen)
        except Exception:  # noqa: BLE001 - una foto rota no debe tumbar la ventana
            return None
    return _cache_fotos[clave]


def abrir_archivo(ruta):
    try:
        os.startfile(ruta)
    except (AttributeError, OSError):
        pass


# ---------- lo que esta PC marco para publicar ----------

def cargar_seleccion():
    try:
        return set(json.loads(SELECCION.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return set()


def guardar_seleccion(nombres):
    LOCAL.mkdir(parents=True, exist_ok=True)
    SELECCION.write_text(json.dumps(sorted(nombres)), encoding="utf-8")


def anotar_historial(accion, detalle):
    nuevo = not HISTORIAL.exists()
    with HISTORIAL.open("a", encoding="utf-8") as f:
        if nuevo:
            f.write("fecha,usuario,accion,detalle\n")
        f.write(f"{datetime.now():%Y-%m-%d %H:%M},{os.environ.get('USERNAME', '')},{accion},\"{detalle}\"\n")


def cuadro_texto(padre, **opciones):
    return tk.Text(padre, bg=FONDO_TEXTO, fg=LETRA_TEXTO, insertbackground=LETRA_TEXTO,
                   relief="flat", borderwidth=8, highlightthickness=0, font=(FUENTE, 10), **opciones)


# ---------- ventana para crear / editar ----------

class Editor(tk.Toplevel):
    def __init__(self, app, carpeta=None, copiar_de=None):
        super().__init__(app)
        self.app = app
        self.carpeta = carpeta
        origen = carpeta or copiar_de
        datos = leer_plantilla(origen) if origen else {}
        self.title("Editar plantilla" if carpeta else "Nueva plantilla")
        self.geometry("900x720")
        self.minsize(760, 600)
        self.transient(app)
        self.grab_set()

        marco = ttk.Frame(self, padding=18)
        marco.pack(fill="both", expand=True)
        marco.columnconfigure(1, weight=1)

        ttk.Label(marco, text=self.title(), font=(FUENTE, 16, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))

        self.titulo = tk.StringVar(value=datos.get("titulo", ""))
        self.precio = tk.StringVar(value=datos.get("precio", ""))
        self.categoria = tk.StringVar(value=datos.get("categoria", ""))
        self.estado = tk.StringVar(value=datos.get("estado", "Nuevo"))

        conocidas = sorted(p.stem for p in CATEGORIAS.glob("*.png")) if CATEGORIAS.exists() else []
        if not self.categoria.get() and conocidas:
            self.categoria.set(conocidas[0])

        def etiqueta(texto, fila):
            ttk.Label(marco, text=texto).grid(row=fila, column=0, sticky="nw", pady=5, padx=(0, 12))

        etiqueta("Título", 1)
        ttk.Entry(marco, textvariable=self.titulo).grid(row=1, column=1, sticky="ew", pady=5)
        etiqueta("Precio (C$)", 2)
        ttk.Entry(marco, textvariable=self.precio, width=14).grid(row=2, column=1, sticky="w", pady=5)
        etiqueta("Categoría", 3)
        ttk.Combobox(marco, textvariable=self.categoria, values=conocidas).grid(row=3, column=1, sticky="ew", pady=5)
        etiqueta("Estado", 4)
        ttk.Combobox(marco, textvariable=self.estado, values=ESTADOS_FB, state="readonly").grid(
            row=4, column=1, sticky="w", pady=5)

        etiqueta("Descripción", 5)
        self.descripcion = cuadro_texto(marco, height=10, wrap="word")
        self.descripcion.grid(row=5, column=1, sticky="nsew", pady=5)
        self.descripcion.insert("1.0", datos.get("descripcion", ""))
        marco.rowconfigure(5, weight=1)

        # Fotos: lista a la izquierda, vista previa grande a la derecha.
        etiqueta("Fotos\n(la 1ª es\nla portada)", 6)
        fotos_marco = ttk.Frame(marco)
        fotos_marco.grid(row=6, column=1, sticky="nsew", pady=5)
        fotos_marco.columnconfigure(0, weight=1)
        self.lista_fotos = tk.Listbox(fotos_marco, height=8, bg=FONDO_TEXTO, fg=LETRA_TEXTO,
                                      selectbackground="#2f6fb0", relief="flat", highlightthickness=0,
                                      activestyle="none", font=(FUENTE, 10), exportselection=False)
        self.lista_fotos.grid(row=0, column=0, rowspan=5, sticky="nsew")
        self.lista_fotos.bind("<<ListboxSelect>>", lambda e: self._ver_foto())
        self.lista_fotos.bind("<Double-1>", lambda e: self._abrir_foto())
        botones_fotos = ttk.Frame(fotos_marco)
        botones_fotos.grid(row=0, column=1, sticky="n", padx=8)
        for texto, accion in [
            ("➕ Agregar…", self._agregar_fotos), ("✖ Quitar", self._quitar_foto),
            ("↑ Subir", lambda: self._mover(-1)), ("↓ Bajar", lambda: self._mover(1)),
        ]:
            ttk.Button(botones_fotos, text=texto, command=accion, width=12).pack(fill="x", pady=2)
        self.vista = ttk.Label(fotos_marco, text="Elige una foto\npara verla aquí", anchor="center",
                               justify="center", width=30)
        self.vista.grid(row=0, column=2, rowspan=5, sticky="nsew")
        fotos_marco.columnconfigure(2, minsize=260)
        self.vista.bind("<Double-1>", lambda e: self._abrir_foto())

        self.fotos = [str(f) for f in datos.get("fotos", [])]
        self._pintar_fotos()
        if self.fotos:
            self.lista_fotos.selection_set(0)
            self._ver_foto()

        botones = ttk.Frame(marco)
        botones.grid(row=7, column=0, columnspan=2, sticky="e", pady=(14, 0))
        ttk.Button(botones, text="Cancelar", command=self.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(botones, text="💾 Guardar", command=self._guardar, style="Accent.TButton").pack(side="right")

    def _pintar_fotos(self):
        self.lista_fotos.delete(0, "end")
        for i, f in enumerate(self.fotos, 1):
            self.lista_fotos.insert("end", f"  {i}. {Path(f).name}")

    def _foto_elegida(self):
        seleccion = self.lista_fotos.curselection()
        return self.fotos[seleccion[0]] if seleccion else None

    def _ver_foto(self):
        ruta = self._foto_elegida()
        imagen = foto_tk(ruta, 260, 220) if ruta else None
        if imagen:
            self.vista.configure(image=imagen, text="")
        else:
            self.vista.configure(image="", text="Elige una foto\npara verla aquí" if not ruta
                                 else "No pude mostrar\nesta foto")

    def _abrir_foto(self):
        if ruta := self._foto_elegida():
            abrir_archivo(ruta)

    def _agregar_fotos(self):
        elegidas = filedialog.askopenfilenames(
            parent=self, title="Elegir fotos",
            filetypes=[("Fotos", "*.jpg *.jpeg *.png *.heic *.heif"), ("Todos", "*.*")],
        )
        if not elegidas:
            return
        self.fotos.extend(elegidas)
        self._pintar_fotos()
        self.lista_fotos.selection_set(len(self.fotos) - 1)
        self._ver_foto()

    def _quitar_foto(self):
        for i in reversed(self.lista_fotos.curselection()):
            del self.fotos[i]
        self._pintar_fotos()
        self._ver_foto()

    def _mover(self, paso):
        seleccion = self.lista_fotos.curselection()
        if not seleccion:
            return
        i = seleccion[0]
        j = i + paso
        if 0 <= j < len(self.fotos):
            self.fotos[i], self.fotos[j] = self.fotos[j], self.fotos[i]
            self._pintar_fotos()
            self.lista_fotos.selection_set(j)

    def _guardar(self):
        datos = {
            "titulo": self.titulo.get().strip(),
            "precio": self.precio.get().strip().replace("C$", "").replace(",", "").strip(),
            "categoria": self.categoria.get().strip(),
            "estado": self.estado.get().strip(),
            "descripcion": self.descripcion.get("1.0", "end"),
        }
        faltan = [k for k in ("titulo", "precio", "categoria", "estado") if not datos[k]]
        if faltan:
            messagebox.showwarning("Faltan datos", "Completa: " + ", ".join(faltan), parent=self)
            return
        if not datos["precio"].isdigit():
            messagebox.showwarning("Precio", "Pon el precio solo en números (puede ser 0).",
                                   parent=self)
            return
        if not self.fotos:
            messagebox.showwarning("Faltan fotos", "Agrega al menos una foto.", parent=self)
            return
        if not (CATEGORIAS / f"{datos['categoria']}.png").exists():
            messagebox.showinfo(
                "Categoría nueva",
                f"El bot todavía no conoce la categoría «{datos['categoria']}». "
                "La primera vez se detendrá y guardará una captura para recortarla.",
                parent=self,
            )
        carpeta = self.carpeta or PUBLICACIONES / nombre_carpeta(datos["titulo"])
        try:
            guardar_plantilla(carpeta, datos, self.fotos)
        except Exception as e:  # noqa: BLE001 - mostrar cualquier error al usuario
            messagebox.showerror("No se pudo guardar", str(e), parent=self)
            return
        self.app.recargar(elegir=carpeta.name)
        self.destroy()


# ---------- ventana principal ----------

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Marketplace bot")
        self.geometry("1280x780")
        self.minsize(1000, 640)
        self.proceso = None
        self.seleccion = cargar_seleccion()
        self.miniaturas = {}

        if sv_ttk:
            sv_ttk.set_theme("dark")
        estilo = ttk.Style(self)
        estilo.configure("Treeview", rowheight=76, font=(FUENTE, 11))
        estilo.configure("Treeview.Heading", font=(FUENTE, 10, "bold"))

        # --- encabezado ---
        arriba = ttk.Frame(self, padding=(18, 14, 18, 8))
        arriba.pack(fill="x")
        textos = ttk.Frame(arriba)
        textos.pack(side="left")
        ttk.Label(textos, text="🛒 Marketplace bot", font=(FUENTE, 20, "bold")).pack(anchor="w")
        self.resumen = ttk.Label(textos, text="", foreground="#9a9a9a")
        self.resumen.pack(anchor="w")
        ttk.Button(arriba, text="📁 Abrir carpeta", command=lambda: abrir_archivo(PUBLICACIONES)).pack(side="right")
        ttk.Button(arriba, text="🗑 Eliminar", command=self.eliminar).pack(side="right", padx=6)
        ttk.Button(arriba, text="📄 Duplicar", command=self.duplicar).pack(side="right")
        ttk.Button(arriba, text="✏️ Editar", command=self.editar).pack(side="right", padx=6)
        ttk.Button(arriba, text="➕ Nueva plantilla", command=self.nueva, style="Accent.TButton").pack(side="right")

        # --- lista a la izquierda, vista previa a la derecha ---
        centro = ttk.Frame(self, padding=(18, 4))
        centro.pack(fill="both", expand=True)
        centro.columnconfigure(0, weight=1)
        centro.rowconfigure(0, weight=1)

        lista = ttk.Frame(centro)
        lista.grid(row=0, column=0, sticky="nsew")
        columnas = ("publicar", "titulo", "precio", "fotos")
        self.tabla = ttk.Treeview(lista, columns=columnas, show="tree headings", selectmode="browse")
        self.tabla.heading("#0", text="")
        self.tabla.column("#0", width=96, stretch=False)
        for col, texto, ancho in [("publicar", "Publicar", 80), ("titulo", "Título", 420),
                                  ("precio", "Precio", 110), ("fotos", "Fotos", 70)]:
            self.tabla.heading(col, text=texto)
            self.tabla.column(col, width=ancho, anchor="center" if col != "titulo" else "w",
                              stretch=col == "titulo")
        barra = ttk.Scrollbar(lista, orient="vertical", command=self.tabla.yview)
        self.tabla.configure(yscrollcommand=barra.set)
        self.tabla.pack(side="left", fill="both", expand=True)
        barra.pack(side="right", fill="y")
        self.tabla.bind("<Button-1>", self._clic_tabla)
        self.tabla.bind("<Double-1>", lambda e: self.editar())
        self.tabla.bind("<<TreeviewSelect>>", lambda e: self._mostrar_detalle())
        self.tabla.bind("<Delete>", lambda e: self.eliminar())
        self.tabla.bind("<space>", lambda e: self._alternar(self.tabla.focus()))

        self._armar_detalle(centro)

        # --- acciones del bot ---
        acciones = ttk.Frame(self, padding=(18, 12, 18, 6))
        # Abajo primero, para que la lista no las empuje fuera de la pantalla.
        acciones.pack(side="bottom", fill="x", before=centro)
        ttk.Button(acciones, text="🚀 Publicar marcados", style="Accent.TButton",
                   command=lambda: self.publicar(True)).pack(side="left")
        ttk.Button(acciones, text="🧪 Prueba (no publica)", command=lambda: self.publicar(False)).pack(
            side="left", padx=6)
        ttk.Separator(acciones, orient="vertical").pack(side="left", fill="y", padx=10)
        ttk.Button(acciones, text="🧹 Borrar publicaciones", command=self.borrar).pack(side="left")
        ttk.Button(acciones, text="🔁 Borrar y publicar", command=self.borrar_y_publicar).pack(side="left", padx=6)
        ttk.Label(acciones, text="Máx. a borrar").pack(side="left", padx=(10, 6))
        self.max_borrar = tk.IntVar(value=20)
        ttk.Spinbox(acciones, from_=1, to=100, width=5, textvariable=self.max_borrar).pack(side="left")
        self.boton_detener = ttk.Button(acciones, text="⏹ Detener", command=self.detener, state="disabled")
        self.boton_detener.pack(side="right")

        self.log = cuadro_texto(self, height=6, state="disabled")
        self.log.configure(font=("Consolas", 10), bg="#141414" if sv_ttk else "#111", fg="#cfcfcf")
        self.log.pack(side="bottom", fill="x", padx=18, pady=(4, 16), before=acciones)
        self.escribir("Marca con un clic en la columna «Publicar» lo que quieres publicar hoy.\n"
                      "Para detener el bot en cualquier momento: botón Detener o lleva el mouse a una esquina.\n")
        self.recargar()

    # --- panel de la derecha ---
    def _armar_detalle(self, padre):
        panel = ttk.Frame(padre, padding=(18, 0, 0, 0), width=420)
        panel.grid(row=0, column=1, sticky="nsew")
        panel.grid_propagate(False)
        panel.columnconfigure(0, weight=1)
        panel.rowconfigure(5, weight=1)

        self.portada = ttk.Label(panel, text="Elige una plantilla", anchor="center", cursor="hand2")
        self.portada.grid(row=0, column=0, sticky="ew", ipady=4)
        self.portada.bind("<Double-1>", lambda e: abrir_archivo(self._foto_grande) if self._foto_grande else None)
        self._foto_grande = None
        ttk.Label(panel, text="Doble clic en la foto para verla completa", foreground="#8a8a8a",
                  font=(FUENTE, 8)).grid(row=1, column=0, pady=(2, 6))
        self.tira = ttk.Frame(panel)
        self.tira.grid(row=2, column=0, sticky="w")

        self.det_titulo = ttk.Label(panel, text="", font=(FUENTE, 13, "bold"), wraplength=400)
        self.det_titulo.grid(row=3, column=0, sticky="w", pady=(10, 0))
        self.det_precio = ttk.Label(panel, text="", font=(FUENTE, 15, "bold"), foreground=ACENTO)
        self.det_precio.grid(row=4, column=0, sticky="w", pady=(2, 6))
        self.det_descripcion = cuadro_texto(panel, wrap="word", height=8, state="disabled")
        self.det_descripcion.grid(row=5, column=0, sticky="nsew")

    def _poner_portada(self, ruta):
        imagen = foto_tk(ruta, 400, 300) if ruta else None
        self._foto_grande = ruta if imagen else None
        self.portada.configure(image=imagen or "", text="" if imagen else "Sin fotos")

    def _mostrar_detalle(self):
        fila = self.tabla.focus()
        for hijo in self.tira.winfo_children():
            hijo.destroy()
        if not fila or not (PUBLICACIONES / fila).exists():
            self._poner_portada(None)
            self.portada.configure(text="Elige una plantilla")
            self.det_titulo.configure(text="")
            self.det_precio.configure(text="")
            self._texto_detalle("")
            return
        datos = leer_plantilla(PUBLICACIONES / fila)
        fotos = datos["fotos"]
        self._poner_portada(fotos[0] if fotos else None)
        for foto in fotos[:6]:
            mini = foto_tk(foto, 60, 60, recortar=True)
            if mini:
                boton = ttk.Label(self.tira, image=mini, cursor="hand2")
                boton.pack(side="left", padx=(0, 6))
                boton.bind("<Button-1>", lambda e, f=foto: self._poner_portada(f))
                boton.bind("<Double-1>", lambda e, f=foto: abrir_archivo(f))
        self.det_titulo.configure(text=datos.get("titulo", fila))
        self.det_precio.configure(text=f"C$ {datos.get('precio', '')}   ·   {datos.get('estado', '')}")
        self._texto_detalle(datos.get("descripcion", ""))

    def _texto_detalle(self, texto):
        self.det_descripcion.configure(state="normal")
        self.det_descripcion.delete("1.0", "end")
        self.det_descripcion.insert("1.0", texto)
        self.det_descripcion.configure(state="disabled")

    # --- lista ---
    def recargar(self, elegir=None):
        elegir = elegir or self.tabla.focus()
        self.tabla.delete(*self.tabla.get_children())
        self.miniaturas.clear()
        plantillas = listar_plantillas()
        for carpeta in plantillas:
            datos = leer_plantilla(carpeta)
            marca = "☑" if carpeta.name in self.seleccion else "☐"
            mini = foto_tk(datos["fotos"][0], 72, 72, recortar=True) if datos["fotos"] else None
            if mini:
                self.miniaturas[carpeta.name] = mini
            self.tabla.insert("", "end", iid=carpeta.name, image=mini or "", values=(
                marca, datos.get("titulo", carpeta.name), f"C$ {datos.get('precio', '')}", len(datos["fotos"])))
        if elegir and self.tabla.exists(elegir):
            self.tabla.selection_set(elegir)
            self.tabla.focus(elegir)
            self.tabla.see(elegir)
        self._actualizar_resumen()
        self._mostrar_detalle()

    def _actualizar_resumen(self):
        total = len(self.tabla.get_children())
        marcadas = sum(1 for f in self.tabla.get_children() if f in self.seleccion)
        self.resumen.configure(text=f"{total} plantillas  ·  {marcadas} marcadas para publicar")

    def _alternar(self, fila):
        if not fila:
            return
        self.seleccion ^= {fila}
        guardar_seleccion(self.seleccion)
        self.tabla.set(fila, "publicar", "☑" if fila in self.seleccion else "☐")
        self._actualizar_resumen()

    def _clic_tabla(self, evento):
        fila = self.tabla.identify_row(evento.y)
        if not fila or self.tabla.identify_column(evento.x) != "#1":
            return None
        # Clic en la casilla: la marca y ademas deja elegida la fila.
        self._alternar(fila)
        self.tabla.selection_set(fila)
        self.tabla.focus(fila)
        return "break"

    def _elegida(self):
        fila = self.tabla.focus() or next(iter(self.tabla.selection()), "")
        if not fila:
            messagebox.showinfo("Elige una", "Primero haz clic en una plantilla de la lista.")
            return None
        return PUBLICACIONES / fila

    def nueva(self):
        Editor(self)

    def editar(self):
        if carpeta := self._elegida():
            Editor(self, carpeta=carpeta)

    def duplicar(self):
        if carpeta := self._elegida():
            Editor(self, copiar_de=carpeta)

    def eliminar(self):
        carpeta = self._elegida()
        if not carpeta:
            return
        titulo = self.tabla.set(carpeta.name, "titulo")
        if not messagebox.askyesno("Eliminar plantilla", f"¿Eliminar «{titulo}» y sus fotos?"):
            return
        # Soltamos las fotos que la ventana tiene abiertas antes de borrar.
        self.portada.configure(image="")
        for hijo in self.tira.winfo_children():
            hijo.destroy()
        try:
            borrar_carpeta(carpeta)
        except OSError as e:
            messagebox.showerror("No se pudo eliminar",
                                 f"Windows no dejó borrar la carpeta:\n{e}\n\n"
                                 "Si la tienes abierta en el Explorador o en Google Drive, ciérrala y prueba otra vez.")
            self.recargar()
            return
        self.seleccion.discard(carpeta.name)
        guardar_seleccion(self.seleccion)
        self.tabla.focus("")
        self.recargar()

    # --- correr los bots ---
    def escribir(self, texto):
        self.log.configure(state="normal")
        self.log.insert("end", texto)
        self.log.see("end")
        self.log.configure(state="disabled")

    def report_callback_exception(self, tipo, valor, rastro):
        # Sin esto, los errores se pierden en silencio (no hay consola).
        self.escribir("⚠ Error: " + "".join(traceback.format_exception(tipo, valor, rastro)))
        messagebox.showerror("Error", f"{valor}\n\nLos detalles quedaron abajo, en el registro.")

    def _correr(self, comandos, al_terminar=None):
        """Corre los comandos uno tras otro, minimizando la ventana mientras tanto."""
        if self.proceso:
            return
        self.boton_detener.configure(state="normal")
        self.iconify()

        registro = CARPETA / "ultimo_registro.txt"  # para revisar despues que paso
        registro.write_text(f"{datetime.now():%Y-%m-%d %H:%M}\n", encoding="utf-8")

        def anotar(linea):
            self.escribir(linea)
            try:
                with registro.open("a", encoding="utf-8") as f:
                    f.write(linea)
            except OSError:
                pass

        def trabajo():
            for comando in comandos:
                self.proceso = subprocess.Popen(
                    [sys.executable, "-u", *comando], cwd=CARPETA, text=True, encoding="utf-8",
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                )
                for linea in self.proceso.stdout:
                    self.after(0, anotar, linea)
                codigo = self.proceso.wait()
                if codigo != 0:
                    self.after(0, anotar, "⚠ El bot se detuvo.\n")
                    break
            self.proceso = None
            self.after(0, self._fin, al_terminar)

        threading.Thread(target=trabajo, daemon=True).start()

    def _fin(self, al_terminar):
        self.boton_detener.configure(state="disabled")
        self.deiconify()
        self.escribir("— Listo —\n")
        if al_terminar:
            al_terminar()

    def detener(self):
        if self.proceso:
            self.proceso.kill()

    def _comando_publicar(self, confirmar):
        marcados = [n for n in sorted(self.seleccion) if (PUBLICACIONES / n / "datos.txt").exists()]
        if not marcados:
            messagebox.showinfo("Nada marcado", "Marca al menos una plantilla en la columna «Publicar».")
            return None, []
        comando = ["publicar_mouse.py", "--solo", *marcados]
        if confirmar:
            comando.append("--confirmar")
        return comando, marcados

    def publicar(self, confirmar):
        comando, marcados = self._comando_publicar(confirmar)
        if not comando:
            return
        if confirmar and not messagebox.askyesno("Publicar", f"¿Publicar {len(marcados)} artículo(s)?"):
            return
        self.escribir(f"\n▶ {'Publicando' if confirmar else 'Probando'}: {', '.join(marcados)}\n")
        fin = (lambda: anotar_historial("publicar", " | ".join(marcados))) if confirmar else None
        self._correr([comando], fin)

    def borrar(self):
        n = self.max_borrar.get()
        if not messagebox.askyesno("Borrar", f"¿Borrar hasta {n} publicaciones de Marketplace?"):
            return
        self.escribir(f"\n▶ Borrando hasta {n} publicaciones\n")
        self._correr([["borrar_mouse.py", "--confirmar", "--max", str(n)]],
                     lambda: anotar_historial("borrar", f"max {n}"))

    def borrar_y_publicar(self):
        comando, marcados = self._comando_publicar(True)
        if not comando:
            return
        n = self.max_borrar.get()
        if not messagebox.askyesno("Borrar y publicar",
                                   f"¿Borrar hasta {n} publicaciones y luego publicar {len(marcados)}?"):
            return
        self.escribir(f"\n▶ Borrando hasta {n} y publicando: {', '.join(marcados)}\n")
        self._correr([["borrar_mouse.py", "--confirmar", "--max", str(n)], comando],
                     lambda: anotar_historial("borrar y publicar", " | ".join(marcados)))


if __name__ == "__main__":
    PUBLICACIONES.mkdir(exist_ok=True)
    App().mainloop()
