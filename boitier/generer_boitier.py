"""Génère le boîtier imprimé en 3D du pavé balance (concept, non testé).

Deux pièces, en millimètres, arêtes extérieures chanfreinées :
  boitier-base.stl  : fond avec les ouvertures USB-C et RJ12
  boitier-dessus.stl : couvercle percé pour 16 touches, avec une lèvre qui s'emboîte

Le solide est découpé en cellules alignées sur les axes, coupées par les plans
de chanfrein. Les faces partagées entre deux cellules pleines disparaissent :
le maillage obtenu est fermé, sans bibliothèque externe.

Usage : python3 generer_boitier.py [dossier_de_sortie]
"""
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
GRILLE_Y0 = 8.0
LED = (58.0, 74.0, 3.2)                     # x, y, côté du trou carré

USB = (12.0, 22.0, 6.0, 11.0)               # x0, x1, z0, z1 dans la paroi arrière
RJ12 = (44.0, 58.0, 3.0, COUPE)             # encoche ouverte vers le haut


def dans(v, a, b):
    return a < v < b


def plein_base(x, y, z):
    if not (0 < x < LARGEUR and 0 < y < LONGUEUR and 0 < z < COUPE):
        return False
    if dans(x, PAROI, LARGEUR - PAROI) and dans(y, PAROI, LONGUEUR - PAROI) and z > FOND:
        return False                                          # cavité
    if y > LONGUEUR - PAROI:
        if dans(x, USB[0], USB[1]) and dans(z, USB[2], USB[3]):
            return False
        if dans(x, RJ12[0], RJ12[1]) and dans(z, RJ12[2], RJ12[3]):
            return False
    return True


def plein_dessus(x, y, z):
    j = PAROI + LEVRE_JEU
    if dans(z, COUPE - LEVRE_HAUTEUR, COUPE):                  # lèvre qui entre dans la base
        dans_levre = dans(x, j, LARGEUR - j) and dans(y, j, LONGUEUR - j)
        creux = dans(x, j + LEVRE_EPAISSEUR, LARGEUR - j - LEVRE_EPAISSEUR) and \
            dans(y, j + LEVRE_EPAISSEUR, LONGUEUR - j - LEVRE_EPAISSEUR)
        if y > LONGUEUR - j - LEVRE_EPAISSEUR and dans(x, RJ12[0] - 1, RJ12[1] + 1):
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
    xs = [0, PAROI, LARGEUR - PAROI, LARGEUR, *USB[:2], *RJ12[:2], CHANFREIN, LARGEUR - CHANFREIN]
    ys = [0, PAROI, LONGUEUR - PAROI, LONGUEUR, CHANFREIN, LONGUEUR - CHANFREIN]
    zs = [0, FOND, COUPE, *USB[2:], RJ12[2], CHANFREIN]
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
