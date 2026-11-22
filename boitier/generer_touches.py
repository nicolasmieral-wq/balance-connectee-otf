"""Capuchons de touches imprimés en 3D : dessus creusé, inscriptions gravées (prototype).

Pour boutons 12 x 12 x 7,3 mm à tige carrée de 3,9 mm dépassant de 3,1 mm
(logement 4,15 mm sur 2,8 mm, entrée chanfreinée : validé à l'essai).

Impression debout, dessus vers le haut, SANS support.
Deux couleurs : changement de filament juste au-dessus de FOND (5,8 mm).
Le fond des gravures reste de la première couleur, tout le dessus prend la
seconde : les inscriptions ressortent en clair sur fond foncé (ou l'inverse).

Chaque capuchon = deux volumes fermés qui se chevauchent (corps + dessus),
que le trancheur fusionne.

Usage : python3 generer_touches.py [dossier] [côté_logement_mm]
"""
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy.spatial import Delaunay

sys.path.insert(0, str(Path(__file__).parent))
from generer_boitier import ecrire_stl, croix, produit, verifier  # noqa: E402

DIAMETRE = 12.0          # passe dans les trous de 12,6 mm du couvercle
BORD = 7.0               # hauteur du bord du capuchon
CHANFREIN = 0.6
CREUX = 0.5              # profondeur de la cuvette au centre
GRAVURE = 0.7            # profondeur des gravures sous le point le plus bas de la cuvette
FOND = BORD - CREUX - GRAVURE      # 5,8 mm : fond plat des gravures (multiple de 0,2)
SOCLE = FOND - 0.2       # dessus du corps, sous la partie gravée
LOGEMENT = 4.15          # validé à l'essai (plaque 4,0 à 4,15 : la 4,15 tient le mieux)
PROFONDEUR = 2.8
ENTREE = 0.4             # chanfrein d'entrée du logement (compense l'écrasement de la 1re couche)
PAS_GRILLE = 0.1         # résolution du dessus gravé (mm)
POLICE = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'

CHIFFRES = ['1', '2', '3', '4', '5', '6', '7', '8', '9', '0', '00', ',']
FONCTIONS = ['effacer', 'P', 'entree', 'A']          # Effacer, Peser, Entrée, Auto


def orienter(tri, normale):
    a, b, c = tri
    n = croix([b[i] - a[i] for i in range(3)], [c[i] - a[i] for i in range(3)])
    return tri if produit(n, normale) >= 0 else (a, c, b)


# ---------- Dessins des inscriptions (image 0/1, 1 = gravé) ----------
def dessin(nom, cote_mm=10.0, res=0.02):
    n = int(cote_mm / res)
    im = Image.new('L', (n, n), 0)
    d = ImageDraw.Draw(im)
    mm = lambda v: v / res
    c = n / 2
    if nom == 'effacer':            # flèche pleine vers la gauche
        d.polygon([(c - mm(3.9), c), (c - mm(0.9), c - mm(3.0)), (c - mm(0.9), c - mm(1.15)),
                   (c + mm(3.7), c - mm(1.15)), (c + mm(3.7), c + mm(1.15)), (c - mm(0.9), c + mm(1.15)),
                   (c - mm(0.9), c + mm(3.0))], fill=255)
    elif nom == 'entree':           # flèche de retour pleine ↵
        d.polygon([(c - mm(3.9), c + mm(1.3)), (c - mm(1.2), c - mm(1.4)), (c - mm(1.2), c + mm(0.2)),
                   (c + mm(1.7), c + mm(0.2)), (c + mm(1.7), c - mm(3.4)), (c + mm(3.7), c - mm(3.4)),
                   (c + mm(3.7), c + mm(2.4)), (c - mm(1.2), c + mm(2.4)), (c - mm(1.2), c + mm(4.0))], fill=255)
    else:
        taille = {'00': 6.2, ',': 11.0}.get(nom, 9.4)       # corps de police (mm)
        epaisseur = {'00': 0.22, ',': 0.35}.get(nom, 0.32)  # épaississement du trait (mm)
        police = ImageFont.truetype(POLICE, int(mm(taille)))
        dy = mm(-1.2) if nom == ',' else 0
        d.text((c, c + dy), nom, font=police, fill=255, anchor='mm', stroke_width=int(mm(epaisseur)), stroke_fill=255)
    return np.array(im, dtype=np.float32) / 255.0, res


def couverture(nom, xs, ys):
    """Part gravée (0..1) autour de chaque nœud de la grille, d'après le dessin sur-échantillonné."""
    img, res = dessin(nom)
    n = img.shape[0]
    k = int(round(PAS_GRILLE / res))
    out = np.zeros((len(ys), len(xs)))
    for j, y in enumerate(ys):
        for i, x in enumerate(xs):
            px, py = int(round(x / res + n / 2)), int(round(-y / res + n / 2))
            a = img[max(0, py - k // 2):py + k // 2 + 1, max(0, px - k // 2):px + k // 2 + 1]
            out[j, i] = a.mean() if a.size else 0
    return out


# ---------- Corps : cylindre chanfreiné, en coupe, avec logement de tige ----------
def corps(cx, cy, logement, n=96):
    r, h, ch, s = DIAMETRE / 2, BORD, CHANFREIN, logement / 2
    ri = r - ch
    t = []
    pt = lambda rr, k: (cx + rr * math.cos(2 * math.pi * k / n), cy + rr * math.sin(2 * math.pi * k / n))
    for k in range(n):
        p, q, a, b = pt(r, k), pt(r, k + 1), pt(ri, k), pt(ri, k + 1)
        nrm = ((p[0] + q[0]) / 2 - cx, (p[1] + q[1]) / 2 - cy, 0)
        t.append(orienter(((*p, 0), (*q, 0), (*q, h - ch)), nrm))
        t.append(orienter(((*p, 0), (*q, h - ch), (*p, h - ch)), nrm))
        t.append(orienter(((*p, h - ch), (*q, h - ch), (*b, h)), (nrm[0], nrm[1], 1)))
        t.append(orienter(((*p, h - ch), (*b, h), (*a, h)), (nrm[0], nrm[1], 1)))
        inv = (-nrm[0], -nrm[1], 0)                       # paroi intérieure de la coupe
        t.append(orienter(((*a, SOCLE), (*b, SOCLE), (*b, h)), inv))
        t.append(orienter(((*a, SOCLE), (*b, h), (*a, h)), inv))
        t.append(orienter(((cx, cy, SOCLE), (*a, SOCLE), (*b, SOCLE)), (0, 0, 1)))
    e = ENTREE / 2
    sq = lambda h: [(cx - h, cy - h), (cx + h, cy - h), (cx + h, cy + h), (cx - h, cy + h)]
    large, carre = sq(s + e), sq(s)
    pts = [pt(r, k) for k in range(n)] + large
    for k in range(1, 4):
        for j in range(24):
            rr = s * 1.5 + (r - s * 1.5) * k / 4
            pts.append((cx + rr * math.cos(2 * math.pi * j / 24), cy + rr * math.sin(2 * math.pi * j / 24)))
    for a, b, c in Delaunay(np.array(pts)).simplices:
        g = [(pts[a][i] + pts[b][i] + pts[c][i]) / 3 for i in (0, 1)]
        if abs(g[0] - cx) < s + e and abs(g[1] - cy) < s + e:
            continue
        t.append(orienter(((*pts[a], 0), (*pts[b], 0), (*pts[c], 0)), (0, 0, -1)))
    for k in range(4):
        nrm = (cx - (carre[k][0] + carre[(k + 1) % 4][0]) / 2, cy - (carre[k][1] + carre[(k + 1) % 4][1]) / 2, 0)
        p0, q0, p, q = large[k], large[(k + 1) % 4], carre[k], carre[(k + 1) % 4]
        t.append(orienter(((*p0, 0), (*q0, 0), (*q, ENTREE)), (nrm[0], nrm[1], -1)))
        t.append(orienter(((*p0, 0), (*q, ENTREE), (*p, ENTREE)), (nrm[0], nrm[1], -1)))
        t.append(orienter(((*p, ENTREE), (*q, ENTREE), (*q, PROFONDEUR)), nrm))
        t.append(orienter(((*p, ENTREE), (*q, PROFONDEUR), (*p, PROFONDEUR)), nrm))
    t.append(orienter(((*carre[0], PROFONDEUR), (*carre[1], PROFONDEUR), (*carre[2], PROFONDEUR)), (0, 0, -1)))
    t.append(orienter(((*carre[0], PROFONDEUR), (*carre[2], PROFONDEUR), (*carre[3], PROFONDEUR)), (0, 0, -1)))
    return t


# ---------- Dessus : surface continue (cuvette + gravures) sur une grille ----------
def dessus(nom, cx, cy):
    ri = DIAMETRE / 2 - CHANFREIN
    rlim = ri + 0.09                     # chevauche légèrement la paroi intérieure du corps
    m = int(math.ceil(rlim / PAS_GRILLE)) + 1
    xs = np.arange(-m, m + 1) * PAS_GRILLE
    ys = xs.copy()
    cov = couverture(nom, xs, ys)
    rs = (ri ** 2 + CREUX ** 2) / (2 * CREUX)          # rayon de la sphère de la cuvette

    def z_cuvette(x, y):
        rho = min(math.hypot(x, y), ri)
        return BORD - CREUX + (rs - math.sqrt(rs * rs - rho * rho))

    # cellules retenues : centre dans le disque
    cel = np.zeros((len(ys) - 1, len(xs) - 1), bool)
    for j in range(len(ys) - 1):
        for i in range(len(xs) - 1):
            cel[j, i] = math.hypot((xs[i] + xs[i + 1]) / 2, (ys[j] + ys[j + 1]) / 2) <= rlim
    zt = np.zeros((len(ys), len(xs)))
    for j, y in enumerate(ys):
        for i, x in enumerate(xs):
            zc = z_cuvette(x, y)
            zt[j, i] = zc - cov[j, i] * (zc - FOND)
    zb = SOCLE - 0.1
    P = lambda i, j, z: (cx + xs[i], cy + ys[j], z)
    t = []
    for j in range(len(ys) - 1):
        for i in range(len(xs) - 1):
            if not cel[j, i]:
                continue
            a, b, c, d = (i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1)
            # dessus : couper selon la diagonale la plus courte en hauteur
            if abs(zt[a[1], a[0]] - zt[c[1], c[0]]) <= abs(zt[b[1], b[0]] - zt[d[1], d[0]]):
                tri = ((a, b, c), (a, c, d))
            else:
                tri = ((a, b, d), (b, c, d))
            for u, v, w in tri:
                t.append(orienter((P(*u, zt[u[1], u[0]]), P(*v, zt[v[1], v[0]]), P(*w, zt[w[1], w[0]])), (0, 0, 1)))
            t.append(orienter((P(*a, zb), P(*b, zb), P(*c, zb)), (0, 0, -1)))
            t.append(orienter((P(*a, zb), P(*c, zb), P(*d, zb)), (0, 0, -1)))
            # parois extérieures en escalier
            for (di, dj), (u, v), nrm in (((0, -1), (a, b), (0, -1, 0)), ((1, 0), (b, c), (1, 0, 0)),
                                          ((0, 1), (c, d), (0, 1, 0)), ((-1, 0), (d, a), (-1, 0, 0))):
                ii, jj = i + di, j + dj
                if 0 <= jj < cel.shape[0] and 0 <= ii < cel.shape[1] and cel[jj, ii]:
                    continue
                t.append(orienter((P(*u, zb), P(*v, zb), P(*v, zt[v[1], v[0]])), nrm))
                t.append(orienter((P(*u, zb), P(*v, zt[v[1], v[0]]), P(*u, zt[u[1], u[0]])), nrm))
    return t


def plateau(noms, logements=None, pas=15.0, colonnes=4):
    t = []
    for k, nom in enumerate(noms):
        cx, cy = (k % colonnes) * pas, -(k // colonnes) * pas
        t += corps(cx, cy, (logements or {}).get(k, LOGEMENT))
        t += dessus(nom, cx, cy)
    return t


if __name__ == '__main__':
    sortie = Path(sys.argv[1] if len(sys.argv) > 1 else '.')
    if len(sys.argv) > 2:
        LOGEMENT = float(sys.argv[2].replace(',', '.'))
    sortie.mkdir(parents=True, exist_ok=True)
    print('corps fermé :', verifier(corps(0, 0, LOGEMENT)), '| dessus fermé :', verifier(dessus('8', 0, 0)))
    ecrire_stl(sortie / 'touches-chiffres.stl', plateau(CHIFFRES), 'touches-chiffres')
    ecrire_stl(sortie / 'touches-fonctions.stl', plateau(FONCTIONS), 'touches-fonctions')
    ecrire_stl(sortie / 'touches-toutes.stl', plateau(CHIFFRES + FONCTIONS), 'touches-toutes')
    essai = {0: 4.0, 1: 4.05, 2: 4.1, 3: 4.15}          # touche 1 = 4,0 ... touche 4 = 4,15 mm
    ecrire_stl(sortie / 'touches-essai-serrage.stl', plateau(['1', '2', '3', '4'], essai), 'touches-essai-serrage')
    print(f'logement {LOGEMENT} mm ; fond des gravures à {FOND:.1f} mm : changer de filament juste au-dessus')
