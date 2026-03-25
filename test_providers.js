#!/usr/bin/env node
/**
 * Provider 深度测试脚本
 * 测试策略：
 * 1. 获取模型列表
 * 2. 测试已知模型
 * 3. 尝试各种模型ID格式
 * 4. 测试不同 headers 组合
 */

import { config } from 'dotenv';
config();

const PROVIDERS = [
  {
    name: 'github',
    baseURL: 'https://models.github.ai/inference',
    apiKeyEnv: 'GITHUB_MODELS_API_KEY',
    testModels: ['gpt-4o-mini', 'gpt-4o', 'o1-mini', 'o1-preview', 'text-embedding-3-small']
  },
  {
    name: 'sambanova',
    baseURL: 'https://api.sambanova.ai/v1',
    apiKeyEnv: 'SAMBANOVA_API_KEY',
    testModels: ['Meta-Llama-3.1-8B-Instruct', 'DeepSeek-V3-0324', 'DeepSeek-V3.1', 'Llama-3.2-90B-Vision-Instruct']
  },
  {
    name: 'openrouter',
    baseURL: 'https://openrouter.ai/api/v1',
    apiKeyEnv: 'OPENROUTER_API_KEY',
    testModels: [
      'openrouter/auto:free',
      'stepfun/step-3.5-flash:free',
      'deepseek/deepseek-chat-v3:free',
      'meta-llama/llama-3.2-3b-instruct:free',
      'microsoft/phi-4:free',
      'huggingfaceh4/zephyr-7b-beta:free'
    ]
  },
  {
    name: 'groq',
    baseURL: 'https://api.groq.com/openai/v1',
    apiKeyEnv: 'GROQ_API_KEY',
    testModels: ['llama-3.1-8b-instant', 'llama-3.3-70b-versatile', 'mixtral-8x7b-32768', 'gemma2-9b-it']
  },
  {
    name: 'opencode',
    baseURL: 'https://opencode.ai/zen/v1',
    apiKeyEnv: 'OPENCODE_API_KEY',
    testModels: ['mimo-v2-omni-free', 'auto', 'claude-3-5-haiku', 'mimo-v1', 'gpt-4o-mini']
  },
  {
    name: 'mistral',
    baseURL: 'https://api.mistral.ai/v1',
    apiKeyEnv: 'MISTRAL_API_KEY',
    testModels: ['mistral-small-latest', 'mistral-medium-latest', 'mistral-large-latest', 'codestral-latest']
  },
  {
    name: 'cerebras',
    baseURL: 'https://api.cerebras.ai/v1',
    apiKeyEnv: 'CEREBRAS_API_KEY',
    testModels: ['llama-3.3-70b', 'llama-3.1-8b']
  },
  {
    name: 'gemini',
    baseURL: 'https://generativelanguage.googleapis.com/v1beta',
    apiKeyEnv: 'GEMINI_API_KEY',
    testModels: ['gemini-2.0-flash', 'gemini-1.5-flash', 'gemini-1.5-pro', 'gemini-pro']
  }
];

const TEST_MESSAGE = "如果你能正常接收到这段指令并准备就绪，请仅回复两个英文字母'ok'，不要输出任何多余的解释、标点符号或执行任何代码操作。";

function buildHeaders(provider, apiKey) {
  if (provider.name === 'gemini') {
    return {
      'x-goog-api-key': apiKey,
      'Content-Type': 'application/json'
    };
  }
  
  const headers = {
    'Authorization': `Bearer ${apiKey}`,
    'Content-Type': 'application/json'
  };
  
  if (provider.name === 'openrouter') {
    headers['HTTP-Referer'] = 'http://localhost:8765';
    headers['X-Title'] = 'OpenRouter Free Proxy';
  }
  
  return headers;
}

async function fetchWithTimeout(url, options, timeout = 15000) {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeout);
  
  try {
    const response = await fetch(url, { ...options, signal: controller.signal });
    clearTimeout(timeoutId);
    return response;
  } catch (error) {
    clearTimeout(timeoutId);
    throw error;
  }
}

async function getModelList(provider, apiKey) {
  try {
    const headers = buildHeaders(provider, apiKey);
    const response = await fetchWithTimeout(`${provider.baseURL}/models`, {
      method: 'GET',
      headers
    }, 10000);
    
    if (!response.ok) {
      return { success: false, status: response.status, statusText: response.statusText, error: await response.text().catch(() => 'Unknown error') };
    }
    
    const data = await response.json();
    return { success: true, models: data.data || data.models || data };
  } catch (error) {
    return { success: false, error: error.message || 'Network error' };
  }
}

async function testChatCompletion(provider, apiKey, modelId) {
  try {
    const headers = buildHeaders(provider, apiKey);
    let url, body;
    
    if (provider.name === 'gemini') {
      const modelPath = modelId.startsWith('models/') ? modelId : `models/${modelId}`;
      url = `${provider.baseURL}/${modelPath}:generateContent`;
      body = JSON.stringify({
        contents: [{ parts: [{ text: TEST_MESSAGE }] }],
        generationConfig: { maxOutputTokens: 10 }
      });
    } else {
      url = `${provider.baseURL}/chat/completions`;
      body = JSON.stringify({
        model: modelId,
        messages: [{ role: 'user', content: TEST_MESSAGE }],
        max_tokens: 10
      });
    }
    
    const response = await fetchWithTimeout(url, {
      method: 'POST',
      headers,
      body
    }, 20000);
    
    const responseText = await response.text();
    let responseData;
    try {
      responseData = JSON.parse(responseText);
    } catch {
      responseData = responseText;
    }
    
    if (!response.ok) {
      return {
        success: false,
        status: response.status,
        statusText: response.statusText,
        error: typeof responseData === 'object' ? responseData : responseText
      };
    }
    
    return { success: true, data: responseData };
  } catch (error) {
    return { success: false, error: error.message || 'Network error' };
  }
}

async function testProvider(provider) {
  const apiKey = process.env[provider.apiKeyEnv];
  
  console.log(`\n${'='.repeat(60)}`);
  console.log(`Testing Provider: ${provider.name.toUpperCase()}`);
  console.log(`${'='.repeat(60)}`);
  
  if (!apiKey) {
    console.log(`❌ API Key not found: ${provider.apiKeyEnv}`);
    return;
  }
  
  console.log(`✓ API Key found: ${apiKey.substring(0, 10)}...${apiKey.slice(-5)}`);
  
  // Step 1: Get Model List
  console.log(`\n📋 Step 1: Fetching model list...`);
  const modelListResult = await getModelList(provider, apiKey);
  
  if (!modelListResult.success) {
    console.log(`❌ Failed to get model list:`);
    console.log(`   Status: ${modelListResult.status || 'N/A'} ${modelListResult.statusText || ''}`);
    console.log(`   Error: ${modelListResult.error || 'Unknown error'}`);
  } else {
    console.log(`✓ Successfully fetched model list`);
    const models = Array.isArray(modelListResult.models) 
      ? modelListResult.models.slice(0, 10).map(m => m.id || m.name || JSON.stringify(m))
      : Object.keys(modelListResult.models).slice(0, 10);
    console.log(`   Available models (first 10): ${models.join(', ')}`);
  }
  
  // Step 2: Test Chat Completions
  console.log(`\n🧪 Step 2: Testing chat completions...`);
  for (const modelId of provider.testModels) {
    process.stdout.write(`   Testing ${modelId}... `);
    const result = await testChatCompletion(provider, apiKey, modelId);
    
    if (result.success) {
      console.log(`✅ OK`);
    } else {
      const errorMsg = result.error?.error?.message || result.error?.message || result.error || result.statusText || 'Unknown error';
      console.log(`❌ ${result.status || 'ERROR'}: ${errorMsg.substring(0, 80)}`);
    }
    
    // Add small delay between requests
    await new Promise(r => setTimeout(r, 500));
  }
}

async function main() {
  console.log('🚀 Starting Provider Deep Test\n');
  console.log(`Test Message: "${TEST_MESSAGE}"`);
  
  for (const provider of PROVIDERS) {
    await testProvider(provider);
    // Add delay between providers
    await new Promise(r => setTimeout(r, 1000));
  }
  
  console.log(`\n${'='.repeat(60)}`);
  console.log('Test Complete');
  console.log(`${'='.repeat(60)}`);
}

main().catch(console.error);
