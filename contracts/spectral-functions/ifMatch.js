// AI RES Spectral function: PATCH/PUT (version-sensitive writes) must declare If-Match.
const names = (op) => (op.parameters || []).map((p) => String((p && p.name) || '').toLowerCase());
module.exports = (op, _o, ctx) =>
  names(op).includes('if-match') ? [] : [{ message: 'PATCH/PUT operation must declare the If-Match header parameter.', path: [...ctx.path] }];
