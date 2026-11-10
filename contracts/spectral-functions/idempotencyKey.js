// AI RES Spectral function: POST with side effects must declare Idempotency-Key.
const names = (op) => (op.parameters || []).map((p) => String((p && p.name) || '').toLowerCase());
module.exports = (op, _o, ctx) =>
  names(op).includes('idempotency-key') ? [] : [{ message: 'POST operation must declare the Idempotency-Key header parameter.', path: [...ctx.path] }];
