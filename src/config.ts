import { readFile, writeFile } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import dotenv from 'dotenv';

dotenv.config();

interface Config {
  default_model: string;
}

const CONFIG_PATH = 'config.json';
const DEFAULT_CONFIG: Config = {
  default_model: 'openrouter/auto:free'
};

let cachedConfig: Config | null = null;

export async function getConfig(): Promise<Config> {
  if (cachedConfig) return cachedConfig;
  
  if (!existsSync(CONFIG_PATH)) {
    await writeFile(CONFIG_PATH, JSON.stringify(DEFAULT_CONFIG, null, 2));
    cachedConfig = DEFAULT_CONFIG;
    return cachedConfig;
  }

  const content = await readFile(CONFIG_PATH, 'utf-8');
  cachedConfig = JSON.parse(content) as Config;
  return cachedConfig;
}

export async function setConfig(config: Partial<Config>): Promise<Config> {
  const currentConfig = await getConfig();
  const newConfig = { ...currentConfig, ...config };
  await writeFile(CONFIG_PATH, JSON.stringify(newConfig, null, 2));
  cachedConfig = newConfig;
  return newConfig;
}

export const ENV = {
  OPENROUTER_API_KEY: process.env.OPENROUTER_API_KEY || '',
  OPENROUTER_BASE_URL: process.env.OPENROUTER_BASE_URL || 'https://openrouter.ai/api/v1',
  PORT: Number(process.env.PORT) || 8765
};
