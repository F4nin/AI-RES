// AI RES Spectral function: 4XX/5XX responses must use application/problem+json (RFC 9457).
module.exports = (responses, _o, ctx) => {
  const out = [];
  for (const [code, r] of Object.entries(responses || {})) {
    if (!/^[45]/.test(code)) continue;
    const content = (r && r.content) || {};
    if (!content['application/problem+json'])
      out.push({ message: `Error response ${code} must use application/problem+json (RFC 9457).`, path: [...ctx.path, code] });
  }
  return out;
};
