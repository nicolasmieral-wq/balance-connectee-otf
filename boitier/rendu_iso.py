"""Vue isométrique éclatée du boîtier et des composants (illustration, cotes indicatives)."""
import math
import struct
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ICI = Path(__file__).parent
sys.path.insert(0, str(ICI))
import generer_boitier as g  # noqa: E402


def lire_stl(p):
    d = Path(p).read_bytes()
    n = struct.unpack('<I', d[80:84])[0]
    out = []
    for i in range(n):
        v = struct.unpack('<12f', d[84 + 50 * i:84 + 50 * i + 48])
        out.append((v[3:6], v[6:9], v[9:12]))
    return out


def boite(x0, y0, z0, dx, dy, dz):
    x1, y1, z1 = x0 + dx, y0 + dy, z0 + dz
    v = [(x, y, z) for z in (z0, z1) for y in (y0, y1) for x in (x0, x1)]
    q = [(0, 2, 3, 1), (4, 5, 7, 6), (0, 1, 5, 4), (2, 6, 7, 3), (0, 4, 6, 2), (1, 3, 7, 5)]
    t = []
    for a, b, c, d in q:
        t += [(v[a], v[b], v[c]), (v[a], v[c], v[d])]
    return t


def decaler(tris, dz):
    return [tuple((p[0], p[1], p[2] + dz) for p in t) for t in tris]


def scene(eclate):
    objets = []
    base = lire_stl(ICI / 'boitier-base.stl')
    dessus = lire_stl(ICI / 'boitier-dessus.stl')
    objets.append((base, (214, 219, 208)))
    h = eclate
    objets.append((decaler(dessus, h), (234, 237, 230)))
    # Pavé : circuit et 16 capuchons, sous le couvercle
    pcb_z = 18.0 + h * 0.42
    objets.append((boite(4, 5, pcb_z, 62, 62, 1.6), (46, 125, 78)))
    objets.append((boite(46, 20, pcb_z - 1.6, 16, 12, 1.6), (40, 90, 160)))
    x_dep = g.LARGEUR / 2 - (3 * g.PAS_TOUCHE + g.TROU_TOUCHE) / 2
    for i in range(4):
        for k in range(4):
            objets.append((boite(x_dep + i * g.PAS_TOUCHE + 0.4, g.GRILLE_Y0 + k * g.PAS_TOUCHE + 0.4,
                                 pcb_z + 1.6, 11.6, 11.6, 7.0), (60, 64, 58)))
    # XIAO ESP32-S3, prise USB-C vers l'arrière
    objets.append((boite(6.5, 69, 2.5, 17.8, 21, 1.2), (36, 70, 140)))
    objets.append((boite(9, 70, 3.7, 12.5, 12, 2.5), (180, 184, 190)))
    objets.append((boite(13, 86, 5.8, 8.6, 6.5, 3.2), (150, 154, 160)))
    # Module MAX3232
    objets.append((boite(27, 70, 2.5, 13, 16, 1.6), (150, 40, 50)))
    objets.append((boite(30, 74, 4.1, 7, 6, 1.8), (30, 30, 30)))
    # Prise RJ12
    objets.append((boite(28.25, 0.5, 2.5, 13.5, 18, 13), (205, 205, 200)))
    # PCF8574 (lecture du pavé)
    return objets


def rendre(objets, chemin, largeur=1900, hauteur=1250, etiquettes=(), camera=(0.95, 1.25, 1.05)):
    """Rendu par tampon de profondeur, sur-échantillonné deux fois."""
    import numpy as np
    C = np.array(camera, float)
    C /= np.linalg.norm(C)
    f = -C
    r = np.cross(f, (0, 0, 1.0))
    r /= np.linalg.norm(r)
    u = np.cross(r, f)
    centre = np.array([35.0, 46.0, 22.0])

    def proj(p):
        q = np.asarray(p, float) - centre
        return np.array([q @ r, -(q @ u), q @ f])

    lum = np.array([-0.35, 0.45, 0.82])
    lum /= np.linalg.norm(lum)
    tris = []
    for t, coul in objets:
        for a, b, c in t:
            n = np.cross(np.subtract(b, a), np.subtract(c, a))
            l = np.linalg.norm(n)
            if l == 0:
                continue
            n /= l
            if n @ C <= 1e-9:
                continue
            s = 0.5 + 0.5 * max(0.0, n @ lum)
            tris.append((proj(a), proj(b), proj(c), np.array(coul) * s))
    pts = np.array([p for t in tris for p in t[:3]])
    ss = 2
    W, H = largeur * ss, hauteur * ss
    k = min((W - 760 * ss) / np.ptp(pts[:, 0]), (H - 220 * ss) / np.ptp(pts[:, 1]))
    off = np.array([(W - np.ptp(pts[:, 0]) * k) / 2 - pts[:, 0].min() * k,
                    (H - np.ptp(pts[:, 1]) * k) / 2 - pts[:, 1].min() * k])
    zbuf = np.full((H, W), np.inf)
    img = np.full((H, W, 3), 255.0)
    for a, b, c, col in tris:
        P = np.array([a[:2], b[:2], c[:2]]) * k + off
        x0, y0 = np.floor(P.min(0)).astype(int)
        x1, y1 = np.ceil(P.max(0)).astype(int)
        x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, W - 1), min(y1, H - 1)
        if x1 < x0 or y1 < y0:
            continue
        ys, xs = np.mgrid[y0:y1 + 1, x0:x1 + 1] + 0.5
        d = (P[1, 1] - P[2, 1]) * (P[0, 0] - P[2, 0]) + (P[2, 0] - P[1, 0]) * (P[0, 1] - P[2, 1])
        if abs(d) < 1e-12:
            continue
        w0 = ((P[1, 1] - P[2, 1]) * (xs - P[2, 0]) + (P[2, 0] - P[1, 0]) * (ys - P[2, 1])) / d
        w1 = ((P[2, 1] - P[0, 1]) * (xs - P[2, 0]) + (P[0, 0] - P[2, 0]) * (ys - P[2, 1])) / d
        w2 = 1 - w0 - w1
        m = (w0 >= -1e-6) & (w1 >= -1e-6) & (w2 >= -1e-6)
        z = w0 * a[2] + w1 * b[2] + w2 * c[2]
        zb = zbuf[y0:y1 + 1, x0:x1 + 1]
        m &= z < zb - 1e-6
        zb[m] = z[m]
        img[y0:y1 + 1, x0:x1 + 1][m] = col
    im = Image.fromarray(img.clip(0, 255).astype('uint8')).resize((largeur, hauteur), Image.LANCZOS)
    d = ImageDraw.Draw(im)
    police = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 25)
    colonnes = {'g': [], 'd': []}
    for texte, p3, cote in etiquettes:
        p = proj(p3)
        colonnes[cote].append((texte, (p[0] * k + off[0]) / ss, (p[1] * k + off[1]) / ss))
    for cote, liste in colonnes.items():
        liste.sort(key=lambda e: e[2])
        y_min = 60
        for texte, x, y in liste:
            ty = max(y, y_min)
            y_min = ty + 64
            tx = 28 if cote == 'g' else largeur - 330
            ancre = 'lm'
            bb = d.textbbox((tx, ty), texte, font=police, anchor=ancre)
            bord = bb[2] + 8 if cote == 'g' else bb[0] - 8
            coude = bord + (30 if cote == 'g' else -30)
            d.line([(x, y), (coude, ty), (bord, ty)], fill=(23, 32, 26), width=3)
            d.ellipse([x - 6, y - 6, x + 6, y + 6], fill=(23, 32, 26))
            d.rectangle([bb[0] - 8, bb[1] - 6, bb[2] + 8, bb[3] + 6], fill=(255, 255, 255), outline=(23, 32, 26), width=2)
            d.text((tx, ty), texte, font=police, fill=(23, 32, 26), anchor=ancre)
    im.save(chemin)


if __name__ == '__main__':
    h = 48
    pz = 18 + h * 0.42
    et = [('Couvercle imprimé (dessus)', (70, 20, 24 + h), 'g'),
          ('Pavé 16 touches + PCF8574', (66, 30, pz), 'g'),
          ('Base imprimée', (70, 30, 9), 'g'),
          ('MAX3232', (34, 82, 4.1), 'd'),
          ('Prise RJ12 (avant)', (35, 0, 12), 'g')]
    rendre(scene(h), ICI / 'vue-isometrique.png', etiquettes=et, camera=(1.0, -1.25, 1.05))
