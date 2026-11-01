import { BlockList, isIP } from 'node:net';

export const normalizeIP = value => typeof value === 'string' && value.startsWith('::ffff:') && isIP(value.slice(7)) === 4 ? value.slice(7) : value;

export function proxyMatcher(entries = []) {
  if (!Array.isArray(entries)) throw new Error('TRUSTED_PROXY_IPS must be an array of IP addresses or CIDRs.');
  const list = new BlockList();
  for (const entry of entries) {
    if (typeof entry !== 'string') throw new Error('TRUSTED_PROXY_IPS contains an invalid address.');
    const parts = entry.split('/');
    const address = normalizeIP(parts[0]);
    const family = isIP(address);
    if (!family || parts.length > 2) throw new Error('TRUSTED_PROXY_IPS contains an invalid address.');
    const type = family === 4 ? 'ipv4' : 'ipv6';
    if (parts.length === 1) list.addAddress(address, type);
    else {
      const prefix = Number(parts[1]);
      // An unrestricted proxy network would trust client-supplied identity headers.
      if (!/^\d+$/.test(parts[1]) || !Number.isInteger(prefix) || prefix < 1 || prefix > (family === 4 ? 32 : 128)) throw new Error('TRUSTED_PROXY_IPS contains an invalid CIDR.');
      list.addSubnet(address, prefix, type);
    }
  }
  return peer => {
    const address = normalizeIP(peer);
    const family = typeof address === 'string' ? isIP(address) : 0;
    return family !== 0 && list.check(address, family === 4 ? 'ipv4' : 'ipv6');
  };
}
