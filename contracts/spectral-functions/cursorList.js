// AI RES Spectral function: Collection GET (operationId starts with "list") must use cursor pagination parameters.
const names = (op) => (op.parameters || []).map((p) => String((p && p.name) || '').toLowerCase());
module.exports = (op, _o, ctx) => {
  if (!/^list/.test(op.operationId || '')) return [];
  const n = names(op).map((x) => x.toLowerCase());
  return n.includes('cursor') && n.includes('limit') ? [] : [{ message: 'list operation must declare cursor and limit query parameters.', path: [...ctx.path] }];
};
