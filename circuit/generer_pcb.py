"""Génère le projet KiCad du pavé balance : schéma, circuit placé et routé.

Concept non testé. Coordonnées du circuit en mm, origine au coin arrière gauche,
y vers l'avant (bord RJ12). Circuit = boîtier décalé de 3,7 mm :
    x_boitier = x_pcb + 3,7     y_boitier = 88,3 - y_pcb

Usage : python3 generer_pcb.py [dossier_de_sortie]
"""
import heapq
import json
import math
import sys
import uuid
from pathlib import Path

import numpy as np

NOM = 'pave-balance'
L_PCB, H_PCB = 62.6, 84.6          # largeur (x), longueur (y)
DX, DY = 100.0, 40.0               # position du circuit sur la feuille KiCad
PISTE, ISOLEMENT, VIA, PERCAGE_VIA = 0.3, 0.2, 0.6, 0.3

_n = 0


def uid():
    global _n
    _n += 1
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f'pave-balance/{_n}'))


RACINE = uid()

# ------------------------------------------------------------------ Empreintes
# Chaque empreinte : pastilles (numéro, x, y, forme, larg, haut, perçage) + contour sérigraphie


def fp_switch():
    p = [('1', 0, 0), ('1', 12.5, 0), ('2', 0, 5), ('2', 12.5, 5)]
    return dict(lib='Button_Switch_THT:SW_PUSH-12mm',
                pads=[(n, x, y, 'oval', 2.2, 1.85, 1.3) for n, x, y in p],   # 2,2 mm : deux touches voisines ont des pastilles à 2,5 mm
                silk=(0.1, -3.65, 12.4, 8.65), crt=(-1.2, -3.75, 13.7, 8.75), ref=(6.25, -4.6))


def fp_dip16():
    pads = []
    for i in range(8):
        pads.append((str(i + 1), 0, 2.54 * i, 'rect' if i == 0 else 'oval', 1.6, 1.6, 0.8))
        pads.append((str(16 - i), 7.62, 2.54 * i, 'oval', 1.6, 1.6, 0.8))
    return dict(lib='Package_DIP:DIP-16_W7.62mm', pads=pads,
                silk=(1.16, -1.33, 6.46, 19.11), crt=(-1.1, -1.55, 8.7, 19.3), ref=(3.81, -2.4))


def fp_cap():
    return dict(lib='Capacitor_THT:C_Disc_D3.0mm_W1.6mm_P2.50mm',
                pads=[('1', 0, 0, 'circle', 1.6, 1.6, 0.8), ('2', 2.5, 0, 'circle', 1.6, 1.6, 0.8)],
                silk=(-0.37, -0.92, 2.87, 0.92), crt=(-1.05, -1.05, 3.55, 1.05), ref=(1.25, -1.9))


def fp_res():
    return dict(lib='Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P7.62mm_Horizontal',
                pads=[('1', 0, 0, 'circle', 1.6, 1.6, 0.8), ('2', 7.62, 0, 'circle', 1.6, 1.6, 0.8)],
                silk=(0.54, -1.37, 7.08, 1.37), crt=(-1.05, -1.5, 8.67, 1.5), ref=(3.81, -2.3))


def fp_led():
    return dict(lib='LED_THT:LED_D3.0mm',
                pads=[('1', 0, 0, 'rect', 1.8, 1.8, 0.9), ('2', 2.54, 0, 'circle', 1.8, 1.8, 0.9)],
                silk=(-0.35, -1.6, 2.9, 1.6), crt=(-1.15, -2.25, 3.7, 2.25), ref=(1.27, -2.9))


def fp_header7():
    return dict(lib='Connector_PinHeader_2.54mm:PinHeader_1x07_P2.54mm_Vertical',
                pads=[(str(i + 1), 0, 2.54 * i, 'rect' if i == 0 else 'oval', 1.7, 1.7, 1.0) for i in range(7)],
                silk=(-1.33, -1.33, 1.33, 16.57), crt=(-1.8, -1.8, 1.8, 17.05), ref=(0, -2.4),
                gfx='B')   # barrette montée par-dessous (XIAO suspendu)


def fp_rj12():
    pads = [(str(i + 1), 1.27 * i, 0 if i % 2 == 0 else 2.54, 'rect' if i == 0 else 'circle', 1.52, 1.52, 0.76)
            for i in range(6)]
    pads += [('', 8.25, 8.89, 'npth', 3.25, 3.25, 3.25), ('', -1.91, 8.89, 'npth', 3.25, 3.25, 3.25)]
    return dict(lib='Connector_RJ:RJ12_Amphenol_54601', pads=pads,
                silk=(-3.43, -1.23, 9.77, 16.77), crt=(-4.04, -1.73, 10.38, 17.27), ref=(3.17, 18.3))


def fp_trou():
    return dict(lib='MountingHole:MountingHole_2.7mm_M2.5', pads=[('', 0, 0, 'npth', 2.7, 2.7, 2.7)],
                silk=None, crt=(-2.95, -2.95, 2.95, 2.95), ref=(0, -3.8), board_only=True)


SYMBOLES_BROCHES = {'MAX3232': {'7': 'T2OUT', '14': 'T1OUT'}, 'XIAO_B': {'1': '5V'},
                    'RJ12': {str(i): f'P{i}' for i in range(1, 7)}}

# ------------------------------------------------------------------ Composants
# (référence, valeur, empreinte, x, y, rotation, face, {pastille: net})
COMPOSANTS = []


def ajouter(ref, valeur, fp, x, y, rot=0, face='F', nets=None, symbole=None, broches=None):
    COMPOSANTS.append(dict(ref=ref, val=valeur, fp=fp, x=x, y=y, rot=rot, face=face, nets=nets or {},
                           sym=symbole, broches=broches))


# Touches : centres sous les trous du couvercle (pas 15 mm), ligne 0 = rangée arrière
COL_X = [8.8, 23.8, 38.8, 53.8]
LIGNE_Y = [18.6, 33.6, 48.6, 63.6]
ETIQUETTES = [['1', '2', '3', 'Effacer'], ['4', '5', '6', 'Peser'], ['7', '8', '9', 'Entrée'],
              ['0', '00', ',', 'Auto']]
n = 1
for r, cy in enumerate(LIGNE_Y):
    for c, cx in enumerate(COL_X):
        ajouter(f'SW{n}', ETIQUETTES[r][c], fp_switch(), cx - 6.25, cy - 2.5,
                nets={'1': f'LIGNE{r}', '2': f'COL{c}'}, symbole='SW')
        n += 1

# XIAO ESP32-S3 sous le circuit, prise USB-C vers la gauche, sur deux barrettes
XIAO_X0 = 2.48
ajouter('J2', 'XIAO D0-D6', fp_header7(), XIAO_X0, 41.3, 90,
        nets={'1': 'LIGNE0', '2': 'LIGNE1', '3': 'LIGNE2', '4': 'LIGNE3', '5': 'COL0', '6': 'COL1', '7': 'COL2'},
        symbole='XIAO_A')
ajouter('J3', 'XIAO 5V-D7', fp_header7(), XIAO_X0, 26.06, 90,
        nets={'1': None, '2': 'GND', '3': '+3V3', '4': 'COL3', '5': 'LED', '6': 'RX2', '7': 'RX1'},
        symbole='XIAO_B')

# MAX3232 couché, broches 1-8 vers l'avant
MAX_X, MAX_Y = 22.0, 9.8
ajouter('U1', 'MAX3232', fp_dip16(), MAX_X, MAX_Y, 90,
        nets={'1': 'C1+', '2': 'V+', '3': 'C1-', '4': 'C2+', '5': 'C2-', '6': 'V-', '7': None, '8': 'BAL_B',
              '9': 'RX2', '10': 'GND', '11': 'GND', '12': 'RX1', '13': 'BAL_A', '14': None, '15': 'GND',
              '16': '+3V3'}, symbole='MAX3232')
ajouter('C1', '100nF', fp_cap(), 16.0, 9.8, 90, nets={'1': 'C1+', '2': 'C1-'}, symbole='C')
ajouter('C2', '100nF', fp_cap(), 12.0, 9.8, 90, nets={'1': 'C2+', '2': 'C2-'}, symbole='C')
ajouter('C3', '100nF', fp_cap(), 43.0, 9.8, 90, nets={'1': 'V+', '2': 'GND'}, symbole='C')
ajouter('C4', '100nF', fp_cap(), 46.0, 9.8, 90, nets={'1': 'V-', '2': 'GND'}, symbole='C')
ajouter('C5', '100nF', fp_cap(), 49.0, 9.8, 90, nets={'1': '+3V3', '2': 'GND'}, symbole='C')
ajouter('R1', '330', fp_res(), 43.5, 2.4, 0, nets={'1': 'LED', '2': 'LED_A'}, symbole='R')
ajouter('D1', 'LED', fp_led(), 52.53, 6.3, 0, nets={'1': 'GND', '2': 'LED_A'}, symbole='LED')

# RJ12 dessous, ouverture vers l'avant, centrée sous l'encoche (x = 31,3)
ajouter('J1', 'RJ12 balance', fp_rj12(), 34.47, 71.0, 180, 'B',
        nets={'1': None, '2': None, '3': 'GND', '4': 'BAL_B', '5': 'BAL_A', '6': None}, symbole='RJ12')

for i, (x, y) in enumerate([(3, 3), (59.6, 3), (3, 81.6), (59.6, 81.6)]):
    ajouter(f'H{i + 1}', 'M2.5', fp_trou(), x, y)

NETS = sorted({v for c in COMPOSANTS for v in c['nets'].values() if v})
NET_ID = {nom: i + 1 for i, nom in enumerate(NETS)}
NC_ID = {}                      # broches libres : nom de net attendu par KiCad
for c in COMPOSANTS:
    c['nc'] = {}
    for num, net in c['nets'].items():
        if net is None:
            noms = dict(SYMBOLES_BROCHES.get(c['sym'], {}))
            c['nc'][num] = f"unconnected-({c['ref']}-{noms.get(num, num)}-Pad{num})"
            NC_ID[c['nc'][num]] = len(NETS) + len(NC_ID) + 1


def position_pastille(c, px, py):
    """Coordonnées circuit d'une pastille (face B : miroir gauche-droite)."""
    if c['face'] == 'B':
        return c['x'] - px, c['y'] + py
    a = math.radians(c['rot'])
    return (c['x'] + px * math.cos(a) + py * math.sin(a), c['y'] - px * math.sin(a) + py * math.cos(a))


def pastilles():
    out = []
    for c in COMPOSANTS:
        for num, px, py, forme, w, h, d in c['fp']['pads']:
            x, y = position_pastille(c, px, py)
            if c['rot'] in (90, 270) and c['face'] == 'F':
                w, h = h, w
            out.append(dict(ref=c['ref'], num=num, x=x, y=y, forme=forme, w=w, h=h, d=d,
                            net=c['nets'].get(num) if num else None))
    return out


# ------------------------------------------------------------------ Routage
PAS = 0.1
NX, NY = int(round(L_PCB / PAS)) + 1, int(round(H_PCB / PAS)) + 1
XS = np.arange(NX) * PAS
YS = np.arange(NY) * PAS
GX, GY = np.meshgrid(XS, YS)          # [y, x]


def dist_pastille(p, x, y):
    dx, dy = np.abs(x - p['x']), np.abs(y - p['y'])
    if p['forme'] in ('circle', 'npth'):
        return np.hypot(dx, dy) - p['w'] / 2
    if p['forme'] == 'rect':
        ex, ey = dx - p['w'] / 2, dy - p['h'] / 2
        return np.where((ex <= 0) & (ey <= 0), np.maximum(ex, ey),
                        np.hypot(np.maximum(ex, 0), np.maximum(ey, 0)))
    r = min(p['w'], p['h']) / 2                       # oblong
    lx, ly = p['w'] / 2 - r, p['h'] / 2 - r
    return np.hypot(np.maximum(dx - lx, 0), np.maximum(dy - ly, 0)) - r


class Grille:
    def __init__(self):
        self.prop = np.full((2, NY, NX), -1, np.int32)   # -1 libre, n = réservé au net n, -2 interdit
        bord = np.minimum.reduce([GX, GY, L_PCB - GX, H_PCB - GY])
        self.prop[:, bord < 0.3 + PISTE / 2 + 0.05] = -2

    def reserver(self, couche, masque, net):
        for l in couche:
            z = self.prop[l]
            libre = masque & (z == -1)
            autre = masque & (z != -1) & (z != net)
            z[libre] = net
            z[autre] = -2

    def utilisable(self, net):
        return (self.prop == -1) | (self.prop == net)


def zone_segment(x0, y0, x1, y1, r):
    lx0, lx1 = int(max(0, (min(x0, x1) - r) / PAS)), int(min(NX - 1, (max(x0, x1) + r) / PAS + 1))
    ly0, ly1 = int(max(0, (min(y0, y1) - r) / PAS)), int(min(NY - 1, (max(y0, y1) + r) / PAS + 1))
    sx, sy = GX[ly0:ly1 + 1, lx0:lx1 + 1], GY[ly0:ly1 + 1, lx0:lx1 + 1]
    vx, vy = x1 - x0, y1 - y0
    l2 = vx * vx + vy * vy
    t = np.clip(((sx - x0) * vx + (sy - y0) * vy) / l2, 0, 1) if l2 else 0
    m = np.hypot(sx - x0 - t * vx, sy - y0 - t * vy) <= r
    full = np.zeros((NY, NX), bool)
    full[ly0:ly1 + 1, lx0:lx1 + 1] = m
    return full


DIRS = [(1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)]


def router(g, net_id, terminaux, cout_via=12.0, cout_virage=0.6):
    """Arbre de Steiner glouton : relie successivement chaque pastille à l'arbre."""
    u = g.utilisable(net_id)
    # via possible si la croix de rayon 0,3 mm est utilisable sur les deux couches
    ok2 = u[0] & u[1]
    via_ok = ok2.copy()
    for k in (1, 2, 3):
        via_ok[k:, :] &= ok2[:-k, :]
        via_ok[:-k, :] &= ok2[k:, :]
        via_ok[:, k:] &= ok2[:, :-k]
        via_ok[:, :-k] &= ok2[:, k:]
    arbre = {(l, j, i) for l in (0, 1) for (j, i) in terminaux[0]}
    restants = list(terminaux[1:])
    chemins = []
    while restants:
        cibles = {}
        for k, t in enumerate(restants):
            for (j, i) in t:
                for l in (0, 1):
                    cibles[(l, j, i)] = k
        centres = [(np.mean([p[1] for p in t]), np.mean([p[0] for p in t])) for t in restants]

        def h(j, i):
            return min(max(abs(i - ci), abs(j - cj)) + 0.414 * min(abs(i - ci), abs(j - cj)) for ci, cj in centres)

        tas, vu, parent = [], {}, {}
        for s in arbre:
            heapq.heappush(tas, (h(s[1], s[2]), 0.0, s, -1))
            vu[(s, -1)] = 0.0
            parent[(s, -1)] = None
        fin = None
        while tas:
            f, c, s, d = heapq.heappop(tas)
            if vu.get((s, d), 1e18) < c:
                continue
            if s in cibles and s not in arbre:
                fin = (s, d)
                break
            l, j, i = s
            for nd, (di, dj) in enumerate(DIRS):
                ni, nj = i + di, j + dj
                if not (0 <= ni < NX and 0 <= nj < NY) or not u[l, nj, ni]:
                    continue
                if di and dj and not (u[l, j, ni] or u[l, nj, i]):
                    continue
                nc = c + (1.414 if di and dj else 1.0) + (cout_virage if d not in (-1, nd) else 0)
                ns = (l, nj, ni)
                if nc < vu.get((ns, nd), 1e18):
                    vu[(ns, nd)] = nc
                    parent[(ns, nd)] = (s, d)
                    heapq.heappush(tas, (nc + h(nj, ni), nc, ns, nd))
            if via_ok[j, i]:
                ns = (1 - l, j, i)
                nc = c + cout_via
                if nc < vu.get((ns, -1), 1e18):
                    vu[(ns, -1)] = nc
                    parent[(ns, -1)] = (s, d)
                    heapq.heappush(tas, (nc + h(j, i), nc, ns, -1))
        if fin is None:
            return None
        chemin, e = [], fin
        while e is not None:
            chemin.append(e[0])
            e = parent[e]
        chemin.reverse()
        k = cibles[fin[0]]
        for (j, i) in restants[k]:
            arbre |= {(0, j, i), (1, j, i)}
        arbre |= set(chemin)
        restants.pop(k)
        chemins.append(chemin)
    return chemins


def simplifier(chemin):
    """Convertit une suite de cellules en segments et vias."""
    segs, vias = [], []
    debut = chemin[0]
    prec = chemin[0]
    dir_prec = None
    for s in chemin[1:]:
        if s[0] != prec[0]:
            if prec != debut:
                segs.append((debut, prec))
            vias.append(prec)
            debut, dir_prec = s, None
        else:
            d = (s[1] - prec[1], s[2] - prec[2])
            if dir_prec is not None and d != dir_prec:
                segs.append((debut, prec))
                debut = prec
            dir_prec = d
        prec = s
    if prec != debut:
        segs.append((debut, prec))
    return segs, vias


def router_tout(pads, ordre):
    g = Grille()
    for p in pads:
        net = NET_ID.get(p['net'], -2) if p['net'] else -2
        if p['forme'] == 'npth':
            g.reserver((0, 1), dist_pastille(p, GX, GY) <= 0.25 + PISTE / 2 + 0.05, -2)
            continue
        g.reserver((0, 1), dist_pastille(p, GX, GY) <= ISOLEMENT + PISTE / 2 + 0.05, net)
    resultat = {}
    for nom in ordre:
        nid = NET_ID[nom]
        terms = []
        for p in pads:
            if p['net'] == nom:
                m = dist_pastille(p, GX, GY) <= -0.15
                js, is_ = np.nonzero(m)
                terms.append(list(zip(js.tolist(), is_.tolist())))
        chemins = router(g, nid, terms)
        if chemins is None:
            return nom, resultat
        resultat[nom] = []
        for ch in chemins:
            segs, vias = simplifier(ch)
            for a, b in segs:
                x0, y0, x1, y1 = a[2] * PAS, a[1] * PAS, b[2] * PAS, b[1] * PAS
                g.reserver((a[0],), zone_segment(x0, y0, x1, y1, PISTE + ISOLEMENT + 0.05), nid)
            for v in vias:
                x, y = v[2] * PAS, v[1] * PAS
                g.reserver((0, 1), zone_segment(x, y, x, y, VIA / 2 + ISOLEMENT + PISTE / 2 + 0.05), nid)
            resultat[nom].append((segs, vias))
    return None, resultat


# ------------------------------------------------------------------ Écriture du circuit
def f(v):
    return f'{v:.4f}'.rstrip('0').rstrip('.')


def ecrire_empreinte(c):
    fp = c['fp']
    cote = c['face']
    B = cote == 'B'
    L = (lambda nom: nom.replace('F.', 'B.')) if B else (lambda nom: nom)
    rot = c['rot']
    ym = (lambda y: -y) if B else (lambda y: y)
    miroir = ' (justify mirror)' if B else ''
    o = [f'  (footprint "{fp["lib"]}" (layer "{"B.Cu" if B else "F.Cu"}") (uuid "{uid()}")',
         f'    (at {f(c["x"] + DX)} {f(c["y"] + DY)}{" " + str(rot) if rot else ""})']
    rx, ry = fp['ref']
    o.append(f'    (property "Reference" "{c["ref"]}" (at {f(rx)} {f(ym(ry))} {rot}) (layer "{L("F.SilkS")}") '
             f'(uuid "{uid()}") (effects (font (size 1 1) (thickness 0.15)){miroir}))')
    o.append(f'    (property "Value" "{c["val"]}" (at {f(rx)} {f(ym(ry) + (-1.6 if B else 1.6))} {rot}) '
             f'(layer "{L("F.Fab")}") (uuid "{uid()}") (effects (font (size 1 1) (thickness 0.15)){miroir}))')
    o.append(f'    (property "Footprint" "{fp["lib"]}" (at 0 0 {rot}) (layer "{L("F.Fab")}") (hide yes) '
             f'(uuid "{uid()}") (effects (font (size 1.27 1.27)){miroir}))')
    if c.get('sym_uuid'):
        o.append(f'    (path "/{c["sym_uuid"]}")')
        o.append(f'    (sheetname "Racine") (sheetfile "{NOM}.kicad_sch")')
    attrs = 'through_hole' if any(p[3] != 'npth' for p in fp['pads']) else ''
    if fp.get('board_only'):
        attrs = 'board_only exclude_from_pos_files exclude_from_bom'
    o.append(f'    (attr {attrs})' if attrs else '    (attr exclude_from_pos_files exclude_from_bom)')
    for nom, rect, w in (('F.SilkS', fp['silk'], 0.12), ('F.CrtYd', fp['crt'], 0.05)):
        if fp.get('gfx') == 'B':
            nom = nom.replace('F.', 'B.')
        if rect:
            x0, y0, x1, y1 = rect
            o.append(f'    (fp_rect (start {f(x0)} {f(ym(y0))}) (end {f(x1)} {f(ym(y1))}) '
                     f'(stroke (width {w}) (type solid)) (fill none) (layer "{L(nom)}") (uuid "{uid()}"))')
    for num, px, py, forme, w, h, d in fp['pads']:
        ang = (rot + (180 if B else 0)) % 360
        a = f' {ang}' if ang else ''
        if forme == 'npth':
            o.append(f'    (pad "" np_thru_hole circle (at {f(px)} {f(ym(py))}{a}) (size {f(w)} {f(h)}) '
                     f'(drill {f(d)}) (layers "*.Cu" "*.Mask") (uuid "{uid()}"))')
            continue
        net = c['nets'].get(num)
        nc = c['nc'].get(num)
        txt_net = f' (net {NET_ID[net]} "/{net}")' if net else (f' (net {NC_ID[nc]} "{nc}")' if nc else '')
        o.append(f'    (pad "{num}" thru_hole {forme} (at {f(px)} {f(ym(py))}{a}) (size {f(w)} {f(h)}) '
                 f'(drill {f(d)}) (layers "*.Cu" "*.Mask" "*.SilkS"){txt_net} (uuid "{uid()}"))'
                 .replace(' "*.SilkS"', ''))
    o.append('  )')
    return '\n'.join(o)


def ecrire_pcb(chemin, routage):
    couches = ['F.Cu', 'B.Cu']
    o = ['(kicad_pcb (version 20240108) (generator "pave_balance_py") (generator_version "8.0")',
         '  (general (thickness 1.6) (legacy_teardrops no))', '  (paper "A4")',
         '  (layers (0 "F.Cu" signal) (31 "B.Cu" signal) (32 "B.Adhes" user "B.Adhesive") '
         '(33 "F.Adhes" user "F.Adhesive") (34 "B.Paste" user) (35 "F.Paste" user) '
         '(36 "B.SilkS" user "B.Silkscreen") (37 "F.SilkS" user "F.Silkscreen") (38 "B.Mask" user) '
         '(39 "F.Mask" user) (40 "Dwgs.User" user "User.Drawings") (41 "Cmts.User" user "User.Comments") '
         '(42 "Eco1.User" user "User.Eco1") (43 "Eco2.User" user "User.Eco2") (44 "Edge.Cuts" user) '
         '(45 "Margin" user) (46 "B.CrtYd" user "B.Courtyard") (47 "F.CrtYd" user "F.Courtyard") '
         '(48 "B.Fab" user) (49 "F.Fab" user))',
         '  (setup (pad_to_mask_clearance 0) (allow_soldermask_bridges_in_footprints no))',
         '  (net 0 "")']
    o += [f'  (net {i} "/{nom}")' for nom, i in NET_ID.items()]
    o += [f'  (net {i} "{nom}")' for nom, i in NC_ID.items()]
    for c in COMPOSANTS:
        o.append(ecrire_empreinte(c))
    o.append(f'  (gr_rect (start {f(DX)} {f(DY)}) (end {f(DX + L_PCB)} {f(DY + H_PCB)}) '
             f'(stroke (width 0.1) (type default)) (fill none) (layer "Edge.Cuts") (uuid "{uid()}"))')
    textes = [('Pavé balance OTF v0.1', 31.3, 14.6, 'F.SilkS', 1.2),
              ('Prototype non testé — essais uniquement', 31.3, 57, 'B.SilkS', 1.0),
              ('XIAO ESP32-S3 dessous, USB à gauche', 11, 33.7, 'B.SilkS', 0.9),
              ('Balance (RJ12)', 31.3, 82.5, 'F.SilkS', 1.0)]
    for t, x, y, couche, taille in textes:
        mir = ' (justify mirror)' if couche.startswith('B') else ''
        o.append(f'  (gr_text "{t}" (at {f(x + DX)} {f(y + DY)} 0) (layer "{couche}") (uuid "{uid()}") '
                 f'(effects (font (size {taille} {taille}) (thickness 0.15)){mir}))')
    for nom, chemins in routage.items():
        nid = NET_ID[nom]
        for segs, vias in chemins:
            for a, b in segs:
                o.append(f'  (segment (start {f(a[2] * PAS + DX)} {f(a[1] * PAS + DY)}) '
                         f'(end {f(b[2] * PAS + DX)} {f(b[1] * PAS + DY)}) (width {PISTE}) '
                         f'(layer "{couches[a[0]]}") (net {nid}) (uuid "{uid()}"))')
            for v in vias:
                o.append(f'  (via (at {f(v[2] * PAS + DX)} {f(v[1] * PAS + DY)}) (size {VIA}) '
                         f'(drill {PERCAGE_VIA}) (layers "F.Cu" "B.Cu") (net {nid}) (uuid "{uid()}"))')
    o.append(')')
    Path(chemin).write_text('\n'.join(o) + '\n', encoding='utf-8')


# ------------------------------------------------------------------ Schéma
SYMBOLES = {
    'SW': ([('1', '~')], [('2', '~')], 'Touche'),
    'C': ([('1', '~')], [('2', '~')], 'C'),
    'R': ([('1', '~')], [('2', '~')], 'R'),
    'LED': ([('2', 'A')], [('1', 'K')], 'LED'),
    'MAX3232': ([('1', 'C1+'), ('3', 'C1-'), ('4', 'C2+'), ('5', 'C2-'), ('2', 'V+'), ('6', 'V-'),
                 ('16', 'VCC'), ('15', 'GND')],
                [('13', 'R1IN'), ('12', 'R1OUT'), ('8', 'R2IN'), ('9', 'R2OUT'), ('11', 'T1IN'),
                 ('14', 'T1OUT'), ('10', 'T2IN'), ('7', 'T2OUT')], 'U'),
    'XIAO_A': ([(str(i + 1), f'D{i}') for i in range(7)], [], 'J'),
    'XIAO_B': ([('1', '5V'), ('2', 'GND'), ('3', '3V3'), ('4', 'D10'), ('5', 'D9'), ('6', 'D8'), ('7', 'D7')],
               [], 'J'),
    'RJ12': ([(str(i + 1), f'P{i + 1}') for i in range(6)], [], 'J'),
}


def geometrie(nom):
    g, d, _ = SYMBOLES[nom]
    n = max(len(g), len(d))
    larg = 10.16 if nom in ('MAX3232',) else (7.62 if len(g) > 1 else 2.54)
    if len(g) <= 1 and len(d) <= 1:
        larg = 5.08
    haut = max(n, 1) * 2.54
    pins = []
    for k, (num, nm) in enumerate(g):
        pins.append((num, nm, -larg / 2 - 2.54, haut / 2 - 1.27 - 2.54 * k, 0))
    for k, (num, nm) in enumerate(d):
        pins.append((num, nm, larg / 2 + 2.54, haut / 2 - 1.27 - 2.54 * k, 180))
    return larg, haut, pins


def lib_symbole(nom):
    larg, haut, pins = geometrie(nom)
    ref = SYMBOLES[nom][2]
    o = [f'    (symbol "pave:{nom}" (pin_names (offset 0.508)) (exclude_from_sim no) (in_bom yes) (on_board yes)',
         f'      (property "Reference" "{ref}" (at 0 {f(haut / 2 + 1.27)} 0) (effects (font (size 1.27 1.27))))',
         f'      (property "Value" "{nom}" (at 0 {f(-haut / 2 - 1.27)} 0) (effects (font (size 1.27 1.27))))',
         '      (property "Footprint" "" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))',
         '      (property "Datasheet" "" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))',
         f'      (symbol "{nom}_0_1" (rectangle (start {f(-larg / 2)} {f(haut / 2)}) (end {f(larg / 2)} {f(-haut / 2)}) '
         '(stroke (width 0.254) (type default)) (fill (type background))))',
         f'      (symbol "{nom}_1_1"']
    for num, nm, x, y, a in pins:
        o.append(f'        (pin passive line (at {f(x)} {f(y)} {a}) (length 2.54) '
                 f'(name "{nm}" (effects (font (size 1.016 1.016)))) (number "{num}" (effects (font (size 1.016 1.016)))))')
    o.append('      )')
    o.append('    )')
    return '\n'.join(o)


def ecrire_schema(chemin):
    o = [f'(kicad_sch (version 20231120) (generator "eeschema") (generator_version "8.0")',
         f'  (uuid "{RACINE}")', '  (paper "A3")',
         '  (title_block (title "Pavé balance OTF") (rev "0.1") (comment 1 "Prototype non testé : essais uniquement, jamais en vente"))',
         '  (lib_symbols']
    o += [lib_symbole(nom) for nom in SYMBOLES]
    o.append('  )')
    places = {}
    # touches : grille 4 x 4
    for k in range(16):
        places[f'SW{k + 1}'] = (40 + (k % 4) * 30, 40 + (k // 4) * 22)
    places.update({'U1': (200, 60), 'C1': (170, 130), 'C2': (195, 130), 'C3': (220, 130), 'C4': (245, 130),
                   'C5': (270, 130), 'R1': (200, 160), 'D1': (240, 160), 'J2': (60, 170), 'J3': (110, 170),
                   'J1': (150, 170)})
    for c in COMPOSANTS:
        if not c['sym']:
            continue
        X, Y = places[c['ref']]
        X, Y = round(X / 2.54) * 2.54, round(Y / 2.54) * 2.54
        larg, haut, pins = geometrie(c['sym'])
        su = uid()
        c['sym_uuid'] = su
        o.append(f'  (symbol (lib_id "pave:{c["sym"]}") (at {f(X)} {f(Y)} 0) (unit 1) (exclude_from_sim no) '
                 f'(in_bom yes) (on_board yes) (dnp no) (uuid "{su}")')
        o.append(f'    (property "Reference" "{c["ref"]}" (at {f(X)} {f(Y - haut / 2 - 1.27)} 0) '
                 '(effects (font (size 1.27 1.27))))')
        o.append(f'    (property "Value" "{c["val"]}" (at {f(X)} {f(Y + haut / 2 + 1.27)} 0) '
                 '(effects (font (size 1.27 1.27))))')
        o.append(f'    (property "Footprint" "{c["fp"]["lib"]}" (at {f(X)} {f(Y)} 0) '
                 '(effects (font (size 1.27 1.27)) (hide yes)))')
        o.append(f'    (property "Datasheet" "" (at {f(X)} {f(Y)} 0) (effects (font (size 1.27 1.27)) (hide yes)))')
        for num, *_ in pins:
            o.append(f'    (pin "{num}" (uuid "{uid()}"))')
        o.append(f'    (instances (project "{NOM}" (path "/{RACINE}" (reference "{c["ref"]}") (unit 1))))')
        o.append('  )')
        for num, nm, x, y, a in pins:
            px, py = X + x, Y - y
            net = c['nets'].get(num)
            if net:
                just = 'right' if a == 0 else 'left'
                o.append(f'  (label "{net}" (at {f(px)} {f(py)} 0) (fields_autoplaced yes) '
                         f'(effects (font (size 1.27 1.27)) (justify {just} bottom)) (uuid "{uid()}"))')
            else:
                o.append(f'  (no_connect (at {f(px)} {f(py)}) (uuid "{uid()}"))')
    o.append('  (sheet_instances (path "/" (page "1")))')
    o.append(')')
    Path(chemin).write_text('\n'.join(o) + '\n', encoding='utf-8')


def ecrire_projet(chemin):
    projet = {
        'board': {'design_settings': {'defaults': {}, 'rules': {'min_clearance': ISOLEMENT, 'min_track_width': 0.2,
                                                                'min_via_diameter': 0.5, 'min_through_hole_diameter': 0.3}}},
        'net_settings': {'classes': [{'name': 'Default', 'clearance': ISOLEMENT, 'track_width': PISTE,
                                      'via_diameter': VIA, 'via_drill': PERCAGE_VIA, 'wire_width': 6,
                                      'bus_width': 12, 'line_style': 0, 'pcb_color': 'rgba(0, 0, 0, 0.000)',
                                      'schematic_color': 'rgba(0, 0, 0, 0.000)', 'priority': 2147483647,
                                      'diff_pair_gap': 0.25, 'diff_pair_via_gap': 0.25, 'diff_pair_width': 0.2,
                                      'microvia_diameter': 0.3, 'microvia_drill': 0.1}],
                         'meta': {'version': 3}},
        'meta': {'filename': f'{NOM}.kicad_pro', 'version': 1},
    }
    Path(chemin).write_text(json.dumps(projet, indent=2), encoding='utf-8')


ORDRE = ['C1+', 'C1-', 'C2+', 'C2-', 'V+', 'V-', 'LED_A', 'LED', 'RX1', 'RX2', 'BAL_A', 'BAL_B', '+3V3', 'GND',
         'LIGNE0', 'LIGNE1', 'LIGNE2', 'LIGNE3', 'COL0', 'COL1', 'COL2', 'COL3']

if __name__ == '__main__':
    sortie = Path(sys.argv[1] if len(sys.argv) > 1 else '.')
    sortie.mkdir(parents=True, exist_ok=True)
    assert sorted(ORDRE) == NETS, set(NETS) ^ set(ORDRE)
    pads = pastilles()
    ordre = list(ORDRE)
    for essai in range(12):
        echec, routage = router_tout(pads, ordre)
        if echec is None:
            break
        print('échec sur', echec, '-> priorité')
        ordre.remove(echec)
        ordre.insert(0, echec)
    else:
        sys.exit('routage impossible')
    print('routé :', len(routage), 'nets, ordre', ordre)
    ecrire_schema(sortie / f'{NOM}.kicad_sch')
    ecrire_pcb(sortie / f'{NOM}.kicad_pcb', routage)
    ecrire_projet(sortie / f'{NOM}.kicad_pro')
    lib = '(kicad_symbol_lib (version 20231120) (generator "pave_balance_py")\n'
    lib += '\n'.join(lib_symbole(nom).replace('(symbol "pave:', '(symbol "') for nom in SYMBOLES) + '\n)\n'
    (sortie / 'pave.kicad_sym').write_text(lib, encoding='utf-8')
    (sortie / 'sym-lib-table').write_text('(sym_lib_table\n  (version 7)\n  (lib (name "pave")(type "KiCad")'
                                          '(uri "${KIPRJMOD}/pave.kicad_sym")(options "")(descr "Pavé balance"))\n)\n',
                                          encoding='utf-8')
    json.dump({'ordre': ordre}, open(sortie / 'routage.json', 'w'))
