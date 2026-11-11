// AI RES Spectral function: POST with side effects must declare Idempotency-Key.
// An operation whose replay would be unsafe or meaningless (credential exchange: a replay must never hand out a stored session) may opt out
// with `x-idempotency-exempt: <non-empty reason>`; the reason is mandatory and reviewed with the overlay (S07, ADR-063).
const names = (op) => (op.parameters || []).map((p) => String((p && p.name) || '').toLowerCase());
module.exports = (op, _o, ctx) => {
  const reason = op['x-idempotency-exempt'];
  if (typeof reason === 'string' && reason.trim().length >= 20) return [];
  return names(op).includes('idempotency-key') ? [] : [{ message: 'POST operation must declare the Idempotency-Key header parameter.', path: [...ctx.path] }];
};
