// AI RES Spectral function: Offset-style pagination is forbidden.
const names = (op) => (op.parameters || []).map((p) => String((p && p.name) || '').toLowerCase());
module.exports = (op, _o, ctx) =>
  names(op).some((x) => /^(offset|page|pagenumber|skip)$/i.test(x))
    ? [{ message: 'offset/page pagination is forbidden; use cursor pagination.', path: [...ctx.path] }] : [];
