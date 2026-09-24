import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js';
import fs from 'fs/promises';
import path from 'path';

let client: Client | null = null;
let connectPromise: Promise<Client> | null = null;

interface McpConfig {
  mcpServers: Record<string, {
    command: string;
    args: string[];
    env?: Record<string, string>;
  }>;
}

async function loadMcpConfig(): Promise<McpConfig> {
  // Keep credentials local; an explicit path also supports shared installations.
  const configPath = process.env.MI3_MCP_CONFIG || path.resolve(process.cwd(), '../.mcp.json');
  const raw = await fs.readFile(configPath, 'utf-8');
  return JSON.parse(raw);
}

async function createClient(): Promise<Client> {
  const config = await loadMcpConfig();
  const serverConfig = config.mcpServers['basement-lab'];
  if (!serverConfig) {
    throw new Error('basement-lab MCP server not found in .mcp.json');
  }

  const transport = new StdioClientTransport({
    command: serverConfig.command,
    args: serverConfig.args,
    env: { ...process.env, ...serverConfig.env } as Record<string, string>,
  });

  const c = new Client({ name: 'mi3-remaster', version: '0.1.0' });
  await c.connect(transport);
  console.log('MCP client connected to basement-lab');

  // List available tools for verification
  const tools = await c.listTools();
  console.log('Available MCP tools:', tools.tools.map(t => t.name).join(', '));

  // Auto-reconnect on close
  transport.onclose = () => {
    console.log('MCP transport closed — will reconnect on next call');
    client = null;
    connectPromise = null;
  };

  return c;
}

export async function getMcpClient(): Promise<Client> {
  if (client) return client;
  if (connectPromise) return connectPromise;

  connectPromise = createClient().then(c => {
    client = c;
    return c;
  }).catch(err => {
    connectPromise = null;
    throw err;
  });

  return connectPromise;
}

export async function callImageLabGenerate(params: {
  prompt: string;
  images?: { base64: string; label?: string }[];
  model?: string;
  aspect_ratio?: string;
  image_size?: string;
}): Promise<{ imageData: Buffer; mimeType: string; text?: string }> {
  const c = await getMcpClient();

  const args: Record<string, unknown> = {
    prompt: params.prompt,
  };
  if (params.images?.length) args.images = params.images;
  if (params.model) args.model = params.model;
  if (params.aspect_ratio) args.aspect_ratio = params.aspect_ratio;
  const validSizes = new Set(['512', '1K', '2K', '4K']);
  if (params.image_size && validSizes.has(params.image_size)) {
    args.image_size = params.image_size;
  }

  console.log('[MCP] callTool imagelab-generate args:', JSON.stringify(args, null, 2));
  const result = await c.callTool({ name: 'imagelab-generate', arguments: args });

  // Parse response — expect image content
  let imageData: Buffer | null = null;
  let mimeType = 'image/png';
  let text: string | undefined;

  if (Array.isArray(result.content)) {
    for (const part of result.content) {
      if (part.type === 'image' && typeof part.data === 'string') {
        imageData = Buffer.from(part.data, 'base64');
        mimeType = (part as { mimeType?: string }).mimeType || 'image/png';
      } else if (part.type === 'text' && typeof part.text === 'string') {
        text = part.text;
      }
    }
  }

  if (!imageData) {
    throw new Error('No image in MCP response: ' + JSON.stringify(result.content).slice(0, 500));
  }

  return { imageData, mimeType, text };
}

export async function callImageLabDescribe(params: {
  image_base64: string;
  focus?: string;
  language?: string;
}): Promise<string> {
  const c = await getMcpClient();
  const result = await c.callTool({ name: 'imagelab-describe', arguments: params });

  if (Array.isArray(result.content)) {
    for (const part of result.content) {
      if (part.type === 'text' && typeof part.text === 'string') {
        return part.text;
      }
    }
  }
  return JSON.stringify(result.content);
}

export async function callImageLabImprovePrompt(params: {
  prompt: string;
  images?: { base64: string }[];
}): Promise<string> {
  const c = await getMcpClient();
  const result = await c.callTool({ name: 'imagelab-improve-prompt', arguments: params });

  if (Array.isArray(result.content)) {
    for (const part of result.content) {
      if (part.type === 'text' && typeof part.text === 'string') {
        return part.text;
      }
    }
  }
  return JSON.stringify(result.content);
}

export function isMcpConnected(): boolean {
  return client !== null;
}

// Eagerly connect on import (don't block, just start)
getMcpClient().catch(err => {
  console.warn('MCP auto-connect failed (will retry on demand):', err.message);
});
