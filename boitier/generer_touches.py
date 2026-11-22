"""Capuchons de touches imprimés en 3D, inscriptions en relief (prototype).

Pour boutons 12 x 12 x 7,3 mm à tige carrée de 3,9 mm dépassant de 3,1 mm.
Le capuchon s'imprime debout, dessus vers le haut, sans support. Les inscriptions
commencent à la hauteur DESSUS : mettre une pause (changement de filament) à
cette hauteur dans le trancheur pour les avoir d'une autre couleur.

Chaque capuchon = deux volumes fermés qui se chevauchent (corps + inscription),
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
from generer_boitier import ecrire_stl, croix, produit  # noqa: E402

DIAMETRE = 12.0          # passe dans les trous de 12,6 mm du couvercle
DESSUS = 6.7             # hauteur du corps ; dépasse d'environ 2 mm du couvercle
CHANFREIN = 0.6
LOGEMENT = 4.1           # côté du logement carré (tige mesurée 3,9 mm)
PROFONDEUR = 2.6         # la tige dépasse de 3,1 mm : 0,5 mm de jeu sous le capuchon
RELIEF = 0.6
POLICE = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'

# Disposition vue de face, rangée du haut d'abord (comme le programme)
CHIFFRES = ['1', '2', '3', '4', '5', '6', '7', '8', '9', '0', '00', ',']
FONCTIONS = ['⌫', '⚖', '↵', 'A']          # Effacer, Peser, Entrée, Auto
TAILLES = {'00': 5.2, ',': 9.0, '⌫': 6.0, '⚖': 7.0, '↵': 7.0}


def orienter(tri, normale):
    a, b, c = tri
    n = croix([b[i] - a[i] for i in range(3)], [c[i] - a[i] for i in range(3)])
    return tri if produit(n, normale) >= 0 else (a, c, b)


def corps(cx, cy, logement, n=96):
    r, h, ch, s = DIAMETRE / 2, DESSUS, CHANFREIN, logement / 2
    t = []
    ext = [(cx + r * math.cos(2 * math.pi * k / n), cy + r * math.sin(2 * math.pi * k / n)) for k in range(n)]
    hau = [(cx + (r - ch) * math.cos(2 * math.pi * k / n), cy + (r - ch) * math.sin(2 * math.pi * k / n)) for k in range(n)]
    carre = [(cx - s, cy - s), (cx + s, cy - s), (cx + s, cy + s), (cx - s, cy + s)]
    for k in range(n):
        p, q = ext[k], ext[(k + 1) % n]
        a, b = hau[k], hau[(k + 1) % n]
        nrm = ((p[0] + q[0]) / 2 - cx, (p[1] + q[1]) / 2 - cy, 0)
        t.append(orienter(((*p, 0), (*q, 0), (*q, h - ch)), nrm))
        t.append(orienter(((*p, 0), (*q, h - ch), (*p, h - ch)), nrm))
        nrm2 = (nrm[0], nrm[1], math.hypot(*nrm[:2]))
        t.append(orienter(((*p, h - ch), (*q, h - ch), (*b, h)), nrm2))
        t.append(orienter(((*p, h - ch), (*b, h), (*a, h)), nrm2))
        t.append(orienter(((cx, cy, h), a, b) if False else ((cx, cy, h), (*a, h), (*b, h)), (0, 0, 1)))
    # dessous : anneau entre le cercle et le carré
    pts = ext + carre
    for k in range(1, 4):                       # points intermédiaires pour une triangulation propre
        for j in range(24):
            ang = 2 * math.pi * j / 24
            rr = s * 1.5 + (r - s * 1.5) * k / 4
            pts.append((cx + rr * math.cos(ang), cy + rr * math.sin(ang)))
    for a, b, c in Delaunay(np.array(pts)).simplices:
        g = [(pts[a][i] + pts[b][i] + pts[c][i]) / 3 for i in (0, 1)]
        if abs(g[0] - cx) < s and abs(g[1] - cy) < s:
            continue
        t.append(orienter(((*pts[a], 0), (*pts[b], 0), (*pts[c], 0)), (0, 0, -1)))
    # logement de la tige
    for k in range(4):
        p, q = carre[k], carre[(k + 1) % 4]
        nrm = (cx - (p[0] + q[0]) / 2, cy - (p[1] + q[1]) / 2, 0)
        t.append(orienter(((*p, 0), (*q, 0), (*q, PROFONDEUR)), nrm))
        t.append(orienter(((*p, 0), (*q, PROFONDEUR), (*p, PROFONDEUR)), nrm))
    t.append(orienter(((*carre[0], PROFONDEUR), (*carre[1], PROFONDEUR), (*carre[2], PROFONDEUR)), (0, 0, -1)))
    t.append(orienter(((*carre[0], PROFONDEUR), (*carre[2], PROFONDEUR), (*carre[3], PROFONDEUR)), (0, 0, -1)))
    return t


def inscription(texte, cx, cy, taille, res=0.04):
    """Relief extrudé depuis une image du texte (pixels fusionnés par lignes)."""
    police = ImageFont.truetype(POLICE, max(8, int(taille / res)))
    cote = int((DIAMETRE - 2 * CHANFREIN - 1.0) / res)
    im = Image.new('L', (cote, cote), 0)
    ImageDraw.Draw(im).text((cote / 2, cote / 2), texte, font=police, fill=255, anchor='mm')
    a = np.array(im) > 127
    z0, z1 = DESSUS - 0.2, DESSUS + RELIEF
    X = lambda i: cx + (i - cote / 2) * res
    Y = lambda j: cy - (j - cote / 2) * res
    t = []
    for j in range(cote):
        i = 0
        while i < cote:
            if not a[j, i]:
                i += 1
                continue
            d = i
            while i < cote and a[j, i]:
                i += 1
            x0, x1, y0, y1 = X(d), X(i), Y(j + 1), Y(j)
            # segment plein [d, i) de la ligne j : boîte, faces partagées laissées (le trancheur répare)
            for z, nz in ((z1, 1), (z0, -1)):
                t.append(orienter(((x0, y0, z), (x1, y0, z), (x1, y1, z)), (0, 0, nz)))
                t.append(orienter(((x0, y0, z), (x1, y1, z), (x0, y1, z)), (0, 0, nz)))
            for (p, q, nrm) in (((x0, y0), (x1, y0), (0, -1, 0)), ((x1, y1), (x0, y1), (0, 1, 0)),
                                ((x1, y0), (x1, y1), (1, 0, 0)), ((x0, y1), (x0, y0), (-1, 0, 0))):
                t.append(orienter(((*p, z0), (*q, z0), (*q, z1)), nrm))
                t.append(orienter(((*p, z0), (*q, z1), (*p, z1)), nrm))
    return t


def plateau(textes, logements=None, pas=15.0, colonnes=4):
    t = []
    for k, txt in enumerate(textes):
        cx, cy = (k % colonnes) * pas, -(k // colonnes) * pas
        t += corps(cx, cy, (logements or {}).get(k, LOGEMENT))
        t += inscription(txt, cx, cy, TAILLES.get(txt, 7.5))
    return t


if __name__ == '__main__':
    sortie = Path(sys.argv[1] if len(sys.argv) > 1 else '.')
    if len(sys.argv) > 2:
        LOGEMENT = float(sys.argv[2].replace(',', '.'))
    sortie.mkdir(parents=True, exist_ok=True)
    ecrire_stl(sortie / 'touches-chiffres.stl', plateau(CHIFFRES), 'touches-chiffres')
    ecrire_stl(sortie / 'touches-fonctions.stl', plateau(FONCTIONS), 'touches-fonctions')
    ecrire_stl(sortie / 'touche-test.stl', plateau(['1', '2', '3'], {0: 3.9, 1: 4.1, 2: 4.3}, colonnes=3),
               'touche-test')
    print('logement', LOGEMENT, 'mm ; changement de filament à', DESSUS, 'mm')
