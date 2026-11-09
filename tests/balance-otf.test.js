const assert = require('assert');
const { creerLecteur, fabriquerTrame, connecterBle, connecterUsb, reconnecterUsb, CONFIG } = require('../balance-otf.js');
const octets = s => Array.from(Buffer.from(s, 'latin1'));
function montage() { const t = { n: 1000 }; return { t, l: creerLecteur(() => t.n) }; }
const cas = [];
const test = (nom, f) => cas.push([nom, f]);

test('trame réelle 245 g', () => { const { l } = montage(); l.recevoir(octets('P+000.245\r')); assert.deepStrictEqual(l.mesure(), { ok: true, kg: 0.245, valeur: '0.245' }); });
test('trame coupée en morceaux', () => { const { l } = montage(); l.recevoir(octets('P+00')); assert.equal(l.mesure().ok, false); l.recevoir(octets('0.245\r')); assert.equal(l.mesure().valeur, '0.245'); });
test('plusieurs trames : la dernière gagne', () => { const { l } = montage(); l.recevoir(octets('P+000.245\rP+001.500\r')); assert.equal(l.mesure().valeur, '1.500'); });
test('début de trame perdu à la connexion : ignoré', () => { const { l } = montage(); l.recevoir(octets('0.245\rP+000.300\r')); assert.equal(l.mesure().valeur, '0.300'); });
test('état stable autre que P', () => { const { l } = montage(); l.recevoir([0x11, ...octets('+000.245\r')]); assert.equal(l.mesure().ok, true); });
test('zéro stable accepté', () => { const { l } = montage(); l.recevoir(octets('P+000.000\r')); assert.equal(l.mesure().valeur, '0.000'); });
test('instable après stable : refus, pas d\'ancien poids', () => { const { l } = montage(); l.recevoir(octets('P+000.245\r')); l.recevoir(fabriquerTrame(0.3, false, false)); assert.equal(l.mesure().ok, false); });
test('surcharge refusée', () => { const { l } = montage(); l.recevoir(fabriquerTrame(30.1, true, true)); assert.equal(l.mesure().raison, 'Balance en surcharge'); });
test('poids négatif refusé', () => { const { l } = montage(); l.recevoir(octets('P-000.100\r')); assert.equal(l.mesure().ok, false); });
test('mesure trop ancienne refusée', () => { const { t, l } = montage(); l.recevoir(octets('P+000.245\r')); t.n += CONFIG.ageMaxMs + 1; assert.equal(l.mesure().raison, 'Mesure trop ancienne'); });
test('trame invalide n\'efface pas et ne remplace pas', () => { const { l } = montage(); l.recevoir(octets('P+000.245\r')); l.recevoir(octets('Pabcdefgh\r')); assert.equal(l.mesure().valeur, '0.245'); });
test('oubli à la déconnexion', () => { const { l } = montage(); l.recevoir(octets('P+000.245\r')); l.oublier(); assert.equal(l.mesure().ok, false); });
test('simulateur : format identique à la balance', () => { assert.deepStrictEqual(fabriquerTrame(0.245, true, false).slice(1), octets('+000.245\r')); });

function faux(aNotif) {
  const ec = {}, carac = { uuid: 'car', properties: { notify: aNotif }, addEventListener: (n, f) => { carac.h = f; }, startNotifications: async () => {} };
  const app = { addEventListener: (n, f) => { ec[n] = f; }, gatt: { connect: async () => ({ getPrimaryServices: async () => [{ uuid: 'srv', getCharacteristics: async () => [carac] }] }), disconnect: () => { app.coupe = true; } } };
  return { carac, ec, app, bt: { requestDevice: async () => app } };
}
test('Bluetooth simulé : réception et déconnexion', async () => {
  const { l } = montage(), f = faux(true); let msg = '';
  const r = await connecterBle(f.bt, l, m => { msg = m; });
  assert.equal(r.caracteristique, 'car');
  const b = new Uint8Array(octets('P+000.245\r'));
  f.carac.h({ target: { value: new DataView(b.buffer) } });
  assert.equal(l.mesure().valeur, '0.245');
  f.ec.gattserverdisconnected();
  assert.equal(l.mesure().ok, false); assert.equal(msg, 'Balance déconnectée');
});
test('Bluetooth sans notification : erreur claire', async () => {
  const { l } = montage(), f = faux(false);
  await assert.rejects(connecterBle(f.bt, l, () => {}), /notification/); assert.ok(f.app.coupe);
});
test('Bluetooth iPad : recherche par nom et service FFE0', async () => {
  const { l } = montage(), f = faux(true); let opt, svc;
  f.bt.requestDevice = async o => { opt = o; return f.app; };
  f.app.gatt.connect = async () => ({ getPrimaryService: async u => { svc = u; return { uuid: u, getCharacteristics: async () => [f.carac] }; } });
  const r = await connecterBle(f.bt, l, () => {}, true);
  assert.deepStrictEqual(opt.filters, [{ namePrefix: 'SH-B30' }]);
  assert.deepStrictEqual(opt.optionalServices, ['0000ffe0-0000-1000-8000-00805f9b34fb']);
  assert.equal(svc, '0000ffe0-0000-1000-8000-00805f9b34fb');
  assert.equal(r.caracteristique, 'car');
});
test('Bluetooth iPad : essaie la forme suivante si Bluefy rejette', async () => {
  const { l } = montage(), f = faux(true), vus = [];
  f.bt.requestDevice = async o => { vus.push(o); if (vus.length < 4) throw 2; return f.app; };
  f.app.gatt.connect = async () => ({ getPrimaryService: async u => ({ uuid: u, getCharacteristics: async () => [f.carac] }) });
  await connecterBle(f.bt, l, () => {}, true);
  assert.equal(vus.length, 4); assert.equal(vus[3].acceptAllDevices, true);
});
test('Bluetooth iPad : détail des échecs', async () => {
  const { l } = montage(), f = faux(true);
  f.bt.requestDevice = async () => { throw 2; };
  await assert.rejects(connecterBle(f.bt, l, () => {}, true), /Essais 1=2, 2=2, 3=2, 4=2/);
});
test('Bluetooth iPad : masque les ajouts de la caisse aux tableaux', async () => {
  Array.prototype.ajoutCaisse = function () { return 1; };
  try {
    const { l } = montage(), f = faux(true); let vus;
    f.bt.requestDevice = async o => { vus = []; for (const k in o.optionalServices) vus.push(k); return f.app; };
    f.app.gatt.connect = async () => ({ getPrimaryService: async u => ({ uuid: u, getCharacteristics: async () => [f.carac] }) });
    await connecterBle(f.bt, l, () => {}, true);
    assert.deepStrictEqual(vus, ['0']);
    assert.equal(typeof [].ajoutCaisse, 'function');
  } finally { delete Array.prototype.ajoutCaisse; }
});
function fauxUsb(opts = {}) {
  const ctl = [], ec = {}, file = (opts.lectures || []).slice();
  const dev = { vendorId: 0x10c4, productId: 0xea60, configuration: null, ctl,
    open: async () => {}, close: async () => { dev.ferme = true; },
    selectConfiguration: async () => { dev.configuration = { interfaces: [{ interfaceNumber: 0, alternate: { endpoints: [{ direction: 'out', type: 'bulk', endpointNumber: 1 }, { direction: 'in', type: 'bulk', endpointNumber: 1 }] } }] }; },
    claimInterface: async () => { if (opts.refus) throw new Error('busy'); },
    controlTransferOut: async (s, d) => { ctl.push([s.request, s.value, d ? [...d] : null, s.requestType, s.recipient, s.index]); return { status: 'ok' }; },
    transferIn: async () => { if (file.length) { const x = file.shift(); if (x === 'err') throw new Error('io'); const b = new Uint8Array(octets(x)); return { status: 'ok', data: new DataView(b.buffer) }; } return new Promise(() => {}); } };
  const usb = { requestDevice: async f => { usb.filtres = f; return dev; }, getDevices: async () => opts.autorises ? [dev] : [], addEventListener: (n, f) => { ec[n] = f; }, removeEventListener: (n) => { delete ec[n]; } };
  return { dev, usb, ec };
}
const pause = () => new Promise(r => setTimeout(r, 5));
test('USB : réglages CP210x 9600 8N1', async () => {
  const { l } = montage(), f = fauxUsb();
  await connecterUsb(f.usb, l, () => {});
  assert.deepStrictEqual(f.usb.filtres, { filters: [{ vendorId: 0x10c4, productId: 0xea60 }] });
  assert.deepStrictEqual(f.dev.ctl.map(c => c.slice(0, 3)), [[0, 1, null], [3, 0x800, null], [0x1e, 0, [0x80, 0x25, 0, 0]], [7, 0x303, null]]);
  assert.ok(f.dev.ctl.every(c => c[3] === 'vendor' && c[4] === 'interface' && c[5] === 0));
});
test('USB : trame en morceaux reconstituée', async () => {
  const { l } = montage(), f = fauxUsb({ lectures: ['P+000', '.245\r'] });
  await connecterUsb(f.usb, l, () => {}); await pause();
  assert.equal(l.mesure().valeur, '0.245');
});
test('USB : débranchement oublie le poids', async () => {
  const { l } = montage(), f = fauxUsb({ lectures: ['P+000.245\r'] }); let m = '';
  await connecterUsb(f.usb, l, x => { m = x; }); await pause();
  f.ec.disconnect({ device: f.dev });
  assert.equal(l.mesure().ok, false); assert.equal(m, 'Câble USB débranché');
});
test('USB : erreur de lecture oublie le poids', async () => {
  const { l } = montage(), f = fauxUsb({ lectures: ['P+000.245\r', 'err'] }); let m = '';
  await connecterUsb(f.usb, l, x => { m = x; }); await pause();
  assert.equal(l.mesure().ok, false); assert.equal(m, 'Liaison USB perdue');
});
test('USB : câble réservé par Android, message clair', async () => {
  const { l } = montage(), f = fauxUsb({ refus: true });
  await assert.rejects(connecterUsb(f.usb, l, () => {}), /réservé/);
});
test('USB : câble déjà autorisé repris, sinon rien', async () => {
  const { l } = montage();
  assert.equal(await reconnecterUsb(fauxUsb().usb, l, () => {}), null);
  assert.ok(await reconnecterUsb(fauxUsb({ autorises: true }).usb, l, () => {}));
});
(async () => { let e = 0; for (const [n, f] of cas) { try { await f(); console.log('ok  ', n); } catch (x) { e++; console.log('ÉCHEC', n, x.message); } } console.log(cas.length - e + '/' + cas.length); process.exit(e ? 1 : 0); })();
