export const LIMITS = Object.freeze({calls:3, maxTokens:256, requestBytes:24576, responseBytes:65536, outputBytes:4096, durationMs:60000, toolCalls:2});
export const MODEL_URL = 'http://127.0.0.1:1/v1/chat/completions';
export const TOOL = Object.freeze({name:'lookup_fixture', description:'Read the synthetic pilot inventory. No real files or services are accessed.', inputSchema:{type:'object',properties:{name:{type:'string',enum:['inventory']}},required:['name'],additionalProperties:false}, route:{connectorId:'pilot',toolName:'lookup_fixture'}});
export function boundedRequest(url, options, calls) {
  if (String(url) !== MODEL_URL || options?.method?.toUpperCase() !== 'POST') throw Error('Destination denied');
  if (calls >= LIMITS.calls) throw Error('Model call limit reached');
  if (typeof options.body !== 'string' || Buffer.byteLength(options.body) > LIMITS.requestBytes) throw Error('Request size limit');
  const body = JSON.parse(options.body);
  if (body.model !== 'agent-free' || !Array.isArray(body.messages) || body.messages.length > 12) throw Error('Model or context denied');
  if (body.tools?.some(t=>t.type!=='function'||t.function?.name!==TOOL.name)) throw Error('Tool denied');
  // Reconstruct the outbound envelope; ignore caller-supplied URLs, headers and overrides.
  return {model:'agent-free',messages:body.messages,stream:true,max_tokens:LIMITS.maxTokens,
    tools:[{type:'function',function:{name:TOOL.name,description:TOOL.description,parameters:TOOL.inputSchema}}],tool_choice:'auto'};
}
export async function boundedResponse(response, signal) {
  if (!response.ok) { await response.body?.cancel(); throw Error('Gateway rejected request ('+response.status+')'); }
  if (!response.headers.get('content-type')?.includes('text/event-stream')) {await response.body?.cancel();throw Error('Unexpected gateway response');}
  const reader=response.body.getReader();let bytes=0, parts=[];
  try {while(true){signal.throwIfAborted();const {done,value}=await reader.read();if(done)break;bytes+=value.byteLength;if(bytes>LIMITS.responseBytes)throw Error('Response size limit');parts.push(value);}return Buffer.concat(parts).toString('utf8');}
  finally {await reader.cancel().catch(()=>{});}
}
export function ownerAllowed(headers,method) {
  return headers.host==='rakazo.144.24.135.201.sslip.io' && headers['remote-user']==='rithvik' && String(headers['remote-groups']||'').split(',').map(x=>x.trim()).includes('admins') && (method==='GET'||headers.origin==='https://rakazo.144.24.135.201.sslip.io');
}
