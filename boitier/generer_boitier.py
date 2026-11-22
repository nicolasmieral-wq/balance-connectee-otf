"""Génère le boîtier imprimé en 3D du pavé balance (concept, non testé).

Deux pièces, en millimètres, arêtes extérieures chanfreinées :
  boitier-base.stl  : fond, ouverture USB-C (côté gauche), encoche RJ12 (avant), 4 plots pour le circuit
  boitier-dessus.stl : couvercle percé pour 16 touches, avec une lèvre qui s'emboîte

Le solide est découpé en cellules alignées sur les axes, coupées par les plans
de chanfrein. Les faces partagées entre deux cellules pleines disparaissent :
le maillage obtenu est fermé, sans bibliothèque externe.

Usage : python3 generer_boitier.py [dossier_de_sortie]
"""
import math
import struct
import sys
from pathlib import Path

# ---------- Dimensions (à ajuster après mesure des composants) ----------
LARGEUR, LONGUEUR, HAUTEUR = 70.0, 92.0, 28.0   # x, y, z extérieurs
PAROI, FOND, DESSUS = 2.0, 2.0, 2.0
CHANFREIN = 2.0
COUPE = 18.0                  # hauteur du joint entre base et couvercle
LEVRE_EPAISSEUR, LEVRE_JEU, LEVRE_HAUTEUR = 1.2, 0.2, 3.0

PAS_TOUCHE, TROU_TOUCHE = 15.0, 12.4       # 4 x 4 touches à capuchon carré de 12 mm
GRILLE_Y0 = 18.5                            # laisse la place à la prise RJ12 sous le circuit
LED = (57.5, 82.0, 3.2)                     # x, y, côté du trou carré

USB = (49.6, 59.6, 2.0, 8.5)                # y0, y1, z0, z1 dans la paroi gauche (XIAO du circuit pave-balance)
RJ12 = (28.0, 42.0, 3.0, COUPE)             # encoche du bord avant, ouverte vers le haut
PLOTS = ((6.7, 6.7), (63.3, 6.7), (6.7, 85.3), (63.3, 85.3))   # sous les trous M2,5 du circuit
PLOT_COTE, PLOT_TROU, PLOT_HAUT = 5.0, 2.2, 17.0               # le circuit repose à z = 17


def dans(v, a, b):
    return a < v < b


def plein_base(x, y, z):
    if not (0 < x < LARGEUR and 0 < y < LONGUEUR and 0 < z < COUPE):
        return False
    for cx, cy in PLOTS:
        if dans(x, cx - PLOT_COTE / 2, cx + PLOT_COTE / 2) and dans(y, cy - PLOT_COTE / 2, cy + PLOT_COTE / 2) \
                and z < PLOT_HAUT:
            return not (dans(x, cx - PLOT_TROU / 2, cx + PLOT_TROU / 2) and
                        dans(y, cy - PLOT_TROU / 2, cy + PLOT_TROU / 2) and z > FOND)
    if dans(x, PAROI, LARGEUR - PAROI) and dans(y, PAROI, LONGUEUR - PAROI) and z > FOND:
        return False                                          # cavité
    if y < PAROI and dans(x, RJ12[0], RJ12[1]) and dans(z, RJ12[2], RJ12[3]):
        return False
    if x < PAROI and dans(y, USB[0], USB[1]) and dans(z, USB[2], USB[3]):
        return False
    return True


def plein_dessus(x, y, z):
    j = PAROI + LEVRE_JEU
    if dans(z, COUPE - LEVRE_HAUTEUR, COUPE):                  # lèvre qui entre dans la base
        dans_levre = dans(x, j, LARGEUR - j) and dans(y, j, LONGUEUR - j)
        creux = dans(x, j + LEVRE_EPAISSEUR, LARGEUR - j - LEVRE_EPAISSEUR) and \
            dans(y, j + LEVRE_EPAISSEUR, LONGUEUR - j - LEVRE_EPAISSEUR)
        if y < j + LEVRE_EPAISSEUR and dans(x, RJ12[0] - 1, RJ12[1] + 1):
            return False                                      # dégagement au-dessus du RJ12
        return dans_levre and not creux
    if not (0 < x < LARGEUR and 0 < y < LONGUEUR and COUPE < z < HAUTEUR):
        return False
    if z < HAUTEUR - DESSUS:
        return not (dans(x, PAROI, LARGEUR - PAROI) and dans(y, PAROI, LONGUEUR - PAROI))
    for (x0, x1), (y0, y1) in trous_dessus():
        if dans(x, x0, x1) and dans(y, y0, y1):
            return False
    return True


def trous_dessus():
    x_depart = LARGEUR / 2 - (3 * PAS_TOUCHE + TROU_TOUCHE) / 2
    for i in range(4):
        for k in range(4):
            x0 = x_depart + i * PAS_TOUCHE
            y0 = GRILLE_Y0 + k * PAS_TOUCHE
            yield (x0, x0 + TROU_TOUCHE), (y0, y0 + TROU_TOUCHE)
    lx, ly, c = LED
    yield (lx - c / 2, lx + c / 2), (ly - c / 2, ly + c / 2)


def plans_chanfrein(bas, haut):
    """Plans n·p <= d qui coupent les arêtes extérieures."""
    c, X, Y = CHANFREIN, LARGEUR, LONGUEUR
    plans = [((1, 1, 0), X + Y - c), ((-1, 1, 0), Y - c), ((1, -1, 0), X - c), ((-1, -1, 0), -c)]
    if bas:
        plans += [((1, 0, -1), X - c), ((-1, 0, -1), -c), ((0, 1, -1), Y - c), ((0, -1, -1), -c)]
    if haut:
        H = HAUTEUR
        plans += [((1, 0, 1), X + H - c), ((-1, 0, 1), H - c), ((0, 1, 1), Y + H - c), ((0, -1, 1), H - c)]
    return plans


def couper(poly, n, d):
    out = []
    for i, p in enumerate(poly):
        q = poly[(i + 1) % len(poly)]
        sp = sum(a * b for a, b in zip(n, p)) - d
        sq = sum(a * b for a, b in zip(n, q)) - d
        if sp <= 1e-9:
            out.append(p)
        if (sp < -1e-9 < sq) or (sq < -1e-9 < sp):
            t = sp / (sp - sq)
            out.append(tuple(a + t * (b - a) for a, b in zip(p, q)))
    return out


def polyedre_cellule(x0, x1, y0, y1, z0, z1, plans):
    v = [(x, y, z) for z in (z0, z1) for y in (y0, y1) for x in (x0, x1)]
    faces = [[v[0], v[2], v[3], v[1]], [v[4], v[5], v[7], v[6]], [v[0], v[1], v[5], v[4]],
             [v[2], v[6], v[7], v[3]], [v[0], v[4], v[6], v[2]], [v[1], v[3], v[7], v[5]]]
    for n, d in plans:
        nouvelles, coupe = [], []
        for f in faces:
            g = couper(f, n, d)
            if len(g) >= 3:
                nouvelles.append(g)
            coupe += [p for p in g if abs(sum(a * b for a, b in zip(n, p)) - d) < 1e-7]
        if not nouvelles:
            return []
        uniques = list({tuple(round(c, 9) for c in p): p for p in coupe}.values())
        if len(uniques) >= 3:
            nouvelles.append(trier_autour(uniques, n))
        faces = nouvelles
    return faces


def trier_autour(pts, n):
    import math
    cx = [sum(p[i] for p in pts) / len(pts) for i in range(3)]
    a = (1, 0, 0) if abs(n[0]) < 0.9 else (0, 1, 0)
    u = croix(n, a)
    w = croix(n, u)
    return sorted(pts, key=lambda p: math.atan2(produit([p[i] - cx[i] for i in range(3)], w),
                                                 produit([p[i] - cx[i] for i in range(3)], u)))


def croix(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def produit(a, b):
    return sum(x * y for x, y in zip(a, b))


def mailler(plein, xs, ys, zs, plans):
    xs, ys, zs = sorted(set(xs)), sorted(set(ys)), sorted(set(zs))
    vues, garder = {}, []
    for i in range(len(xs) - 1):
        for j in range(len(ys) - 1):
            for k in range(len(zs) - 1):
                c = ((xs[i] + xs[i + 1]) / 2, (ys[j] + ys[j + 1]) / 2, (zs[k] + zs[k + 1]) / 2)
                if not plein(*c):
                    continue
                faces = polyedre_cellule(xs[i], xs[i + 1], ys[j], ys[j + 1], zs[k], zs[k + 1], plans)
                pts = [p for f in faces for p in f]
                if pts:  # centre de la cellule coupée, pour orienter les faces vers l'extérieur
                    c = tuple(sum(p[n] for p in pts) / len(pts) for n in range(3))
                for f in faces:
                    cle = frozenset(tuple(round(v, 6) for v in p) for p in f)
                    vues[cle] = vues.get(cle, 0) + 1
                    garder.append((cle, f, c))
    triangles = []
    for cle, f, c in garder:
        if vues[cle] != 1:
            continue
        n = croix([f[1][i] - f[0][i] for i in range(3)], [f[2][i] - f[0][i] for i in range(3)])
        if produit(n, [f[0][i] - c[i] for i in range(3)]) < 0:
            f = f[::-1]
        for t in range(1, len(f) - 1):
            triangles.append((f[0], f[t], f[t + 1]))
    return triangles


def ecrire_stl(chemin, triangles, nom):
    with open(chemin, 'wb') as s:
        s.write(nom.encode().ljust(80, b' ')[:80])
        s.write(struct.pack('<I', len(triangles)))
        for a, b, c in triangles:
            n = croix([b[i] - a[i] for i in range(3)], [c[i] - a[i] for i in range(3)])
            l = produit(n, n) ** 0.5 or 1
            s.write(struct.pack('<12fH', *(x / l for x in n), *a, *b, *c, 0))


def base():
    xs = [0, PAROI, LARGEUR - PAROI, LARGEUR, *RJ12[:2], CHANFREIN, LARGEUR - CHANFREIN]
    ys = [0, PAROI, LONGUEUR - PAROI, LONGUEUR, *USB[:2], CHANFREIN, LONGUEUR - CHANFREIN]
    zs = [0, FOND, COUPE, *USB[2:], RJ12[2], CHANFREIN, PLOT_HAUT]
    for cx, cy in PLOTS:
        xs += [cx - PLOT_COTE / 2, cx + PLOT_COTE / 2, cx - PLOT_TROU / 2, cx + PLOT_TROU / 2]
        ys += [cy - PLOT_COTE / 2, cy + PLOT_COTE / 2, cy - PLOT_TROU / 2, cy + PLOT_TROU / 2]
    return mailler(plein_base, xs, ys, zs, plans_chanfrein(bas=True, haut=False))


def dessus():
    j = PAROI + LEVRE_JEU
    e = j + LEVRE_EPAISSEUR
    xs = [0, PAROI, LARGEUR - PAROI, LARGEUR, j, e, LARGEUR - j, LARGEUR - e, RJ12[0] - 1, RJ12[1] + 1,
          CHANFREIN, LARGEUR - CHANFREIN]
    ys = [0, PAROI, LONGUEUR - PAROI, LONGUEUR, j, e, LONGUEUR - j, LONGUEUR - e, CHANFREIN, LONGUEUR - CHANFREIN]
    for (x0, x1), (y0, y1) in trous_dessus():
        xs += [x0, x1]
        ys += [y0, y1]
    zs = [COUPE - LEVRE_HAUTEUR, COUPE, HAUTEUR - DESSUS, HAUTEUR, HAUTEUR - CHANFREIN]
    return mailler(plein_dessus, xs, ys, zs, plans_chanfrein(bas=False, haut=True))


# ---------- Couvercle à trous ronds (capuchons ronds) ----------
def centres_trous():
    """Centres des 16 touches, puis de la LED."""
    x_depart = LARGEUR / 2 - (3 * PAS_TOUCHE + TROU_TOUCHE) / 2
    for i in range(4):
        for k in range(4):
            yield x_depart + i * PAS_TOUCHE + TROU_TOUCHE / 2, GRILLE_Y0 + k * PAS_TOUCHE + TROU_TOUCHE / 2


def plaque_ronde(diam, diam_led, segments=72):
    """Dessus du couvercle (z de HAUTEUR - DESSUS à HAUTEUR), chanfreiné, percé de trous ronds.
    Coque fermée indépendante ; elle chevauche les parois, ce que les trancheurs fusionnent."""
    import numpy as np
    from scipy.spatial import Delaunay
    X, Y, c, H = LARGEUR, LONGUEUR, CHANFREIN, HAUTEUR
    zb, zh = H - DESSUS, H
    trous = [(cx, cy, diam / 2) for cx, cy in centres_trous()] + [(LED[0], LED[1], diam_led / 2)]

    def anneau(cx, cy, r, n):
        return [(cx + r * math.cos(2 * math.pi * (k + .5) / n), cy + r * math.sin(2 * math.pi * (k + .5) / n))
                for k in range(n)]

    polys = [anneau(cx, cy, r, segments if r > 3 else 24) for cx, cy, r in trous]
    pas = 1.0
    xs = list(np.arange(c, X - c + 1e-9, pas))
    if xs[-1] < X - c - 1e-6:
        xs.append(X - c)
    ys = list(np.arange(c, Y - c + 1e-9, pas))
    if ys[-1] < Y - c - 1e-6:
        ys.append(Y - c)
    # contour du dessus (rectangle rentré de c) et du dessous (octogone), mêmes abscisses
    haut = [(x, c) for x in xs] + [(X - c, y) for y in ys[1:]] + [(x, Y - c) for x in xs[-2::-1]] + \
           [(c, y) for y in ys[-2:0:-1]]
    bas = [(x, 0.0) for x in xs] + [(X, y) for y in ys] + [(x, Y) for x in xs[::-1]] + [(0.0, y) for y in ys[::-1]]

    def loin_des_trous(x, y, m):
        return all(math.hypot(x - cx, y - cy) > r + m for cx, cy, r in trous)

    def triangule(contour, interieur):
        pts = list(contour) + [p for poly in polys for p in poly]
        for x in np.arange(c + 1.5, X - c - 1.0, 1.6):
            for y in np.arange(c + 1.5, Y - c - 1.0, 1.6):
                if loin_des_trous(x, y, 1.0):
                    pts.append((float(x), float(y)))
        tri = Delaunay(np.array(pts))
        res = []
        for a, b, d in tri.simplices:
            g = ((pts[a][0] + pts[b][0] + pts[d][0]) / 3, (pts[a][1] + pts[b][1] + pts[d][1]) / 3)
            if interieur(*g) and loin_des_trous(g[0], g[1], -0.02) and \
                    not any(math.hypot(g[0] - cx, g[1] - cy) < r * math.cos(math.pi / (segments if r > 3 else 24)) - 1e-6
                            for cx, cy, r in trous):
                res.append((pts[a], pts[b], pts[d]))
        return res

    triangles = []

    def ajouter(tri3d, normale):
        a, b, d = tri3d
        n = croix([b[i] - a[i] for i in range(3)], [d[i] - a[i] for i in range(3)])
        if produit(n, normale) < 0:
            tri3d = (a, d, b)
        triangles.append(tri3d)

    dedans_haut = lambda x, y: c - 1e-9 <= x <= X - c + 1e-9 and c - 1e-9 <= y <= Y - c + 1e-9
    dedans_bas = lambda x, y: 0 <= x <= X and 0 <= y <= Y and x + y >= c and (X - x) + y >= c and \
        x + (Y - y) >= c and (X - x) + (Y - y) >= c
    for a, b, d in triangule(haut, dedans_haut):
        ajouter(((a[0], a[1], zh), (b[0], b[1], zh), (d[0], d[1], zh)), (0, 0, 1))
    for a, b, d in triangule(bas, dedans_bas):
        ajouter(((a[0], a[1], zb), (b[0], b[1], zb), (d[0], d[1], zb)), (0, 0, -1))
    # parois des trous (normale vers le centre du trou)
    for (cx, cy, r), poly in zip(trous, polys):
        for k in range(len(poly)):
            p, q = poly[k], poly[(k + 1) % len(poly)]
            mx, my = (p[0] + q[0]) / 2, (p[1] + q[1]) / 2
            nrm = (cx - mx, cy - my, 0)
            ajouter(((p[0], p[1], zb), (q[0], q[1], zb), (q[0], q[1], zh)), nrm)
            ajouter(((p[0], p[1], zb), (q[0], q[1], zh), (p[0], p[1], zh)), nrm)
    # chanfreins des quatre bords
    def bande(h_pts, b_pts, nrm):
        for i in range(len(h_pts) - 1):
            ajouter(((*b_pts[i], zb), (*b_pts[i + 1], zb), (*h_pts[i + 1], zh)), nrm)
            ajouter(((*b_pts[i], zb), (*h_pts[i + 1], zh), (*h_pts[i], zh)), nrm)
    bande([(x, c) for x in xs], [(x, 0.0) for x in xs], (0, -1, 1))
    bande([(x, Y - c) for x in xs], [(x, Y) for x in xs], (0, 1, 1))
    bande([(c, y) for y in ys], [(0.0, y) for y in ys], (-1, 0, 1))
    bande([(X - c, y) for y in ys], [(X, y) for y in ys], (1, 0, 1))
    # quatre coins
    for (hx, hy), (b1, b2), nrm in (((c, c), ((c, 0.0), (0.0, c)), (-1, -1, 1)),
                                     ((X - c, c), ((X - c, 0.0), (X, c)), (1, -1, 1)),
                                     ((c, Y - c), ((c, Y), (0.0, Y - c)), (-1, 1, 1)),
                                     ((X - c, Y - c), ((X - c, Y), (X, Y - c)), (1, 1, 1))):
        ajouter(((hx, hy, zh), (*b1, zb), (*b2, zb)), nrm)
    return triangles


def murs_dessus():
    """Couvercle sans sa plaque : parois et lèvre, montées 0,5 mm dans la plaque."""
    z_haut = HAUTEUR - DESSUS + 0.5

    def plein(x, y, z):
        if z > z_haut:
            return False
        if z > HAUTEUR - DESSUS and dans(x, PAROI, LARGEUR - PAROI) and dans(y, PAROI, LONGUEUR - PAROI):
            return False
        return plein_dessus(x, y, z) if z < HAUTEUR - DESSUS else (0 < x < LARGEUR and 0 < y < LONGUEUR)

    j = PAROI + LEVRE_JEU
    e = j + LEVRE_EPAISSEUR
    xs = [0, PAROI, LARGEUR - PAROI, LARGEUR, j, e, LARGEUR - j, LARGEUR - e, RJ12[0] - 1, RJ12[1] + 1,
          CHANFREIN, LARGEUR - CHANFREIN]
    ys = [0, PAROI, LONGUEUR - PAROI, LONGUEUR, j, e, LONGUEUR - j, LONGUEUR - e, CHANFREIN, LONGUEUR - CHANFREIN]
    zs = [COUPE - LEVRE_HAUTEUR, COUPE, HAUTEUR - DESSUS, z_haut]
    return mailler(plein, xs, ys, zs, plans_chanfrein(bas=False, haut=True))


DIAM_ROND = 12.6       # diamètre des trous ronds : diamètre du capuchon + 0,5 mm


def verifier(triangles):
    """Chaque arête doit être partagée par exactement deux triangles, en sens opposés."""
    aretes = {}
    for t in triangles:
        for i in range(3):
            a = tuple(round(v, 5) for v in t[i])
            b = tuple(round(v, 5) for v in t[(i + 1) % 3])
            aretes[(a, b)] = aretes.get((a, b), 0) + 1
    return all(aretes.get((b, a), 0) == n for (a, b), n in aretes.items())


if __name__ == '__main__':
    sortie = Path(sys.argv[1] if len(sys.argv) > 1 else '.')
    sortie.mkdir(parents=True, exist_ok=True)
    for nom, tri in (('boitier-base', base()), ('boitier-dessus', dessus())):
        ecrire_stl(sortie / (nom + '.stl'), tri, nom)
        print(nom, len(tri), 'triangles', 'fermé' if verifier(tri) else 'NON FERMÉ')
    # Variante pour capuchons ronds : deux coques fermées dans le même fichier
    murs, plaque = murs_dessus(), plaque_ronde(DIAM_ROND, LED[2])
    ecrire_stl(sortie / 'boitier-dessus-rond.stl', murs + plaque, 'boitier-dessus-rond')
    print('boitier-dessus-rond', len(murs) + len(plaque), 'triangles,',
          'parois', 'fermées' if verifier(murs) else 'NON FERMÉES', '/ plaque', 'fermée' if verifier(plaque) else 'NON FERMÉE')
