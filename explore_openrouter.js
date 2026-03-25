#!/usr/bin/env node
/**
 * OpenRouter 免费模型深度探索
 */

import { config } from 'dotenv';
config();

const OPENROUTER_API_KEY = process.env.OPENROUTER_API_KEY;
const BASE_URL = 'https://openrouter.ai/api/v1';

const headers = {
  'Authorization': `Bearer ${OPENROUTER_API_KEY}`,
  'HTTP-Referer': 'http://localhost:8765',
  'X-Title': 'OpenRouter Free Proxy',
  'Content-Type': 'application/json'
};

const TEST_MESSAGE = "如果你能正常接收到这段指令并准备就绪，请仅回复两个英文字母'ok'，不要输出任何多余的解释、标点符号或执行任何代码操作。";

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

async function getAllModels() {
  console.log('📋 Fetching all available models from OpenRouter...\n');
  
  try {
    const response = await fetchWithTimeout(`${BASE_URL}/models`, {
      method: 'GET',
      headers
    }, 20000);
    
    if (!response.ok) {
      console.log(`❌ Failed: ${response.status} ${response.statusText}`);
      return [];
    }
    
    const data = await response.json();
    const models = data.data || [];
    
    // Filter for free models
    const freeModels = models.filter(m => m.id && m.id.includes(':free'));
    
    console.log(`✓ Total models: ${models.length}`);
    console.log(`✓ Free models: ${freeModels.length}\n`);
    
    return freeModels.map(m => ({
      id: m.id,
      name: m.name,
      context: m.context_length,
      pricing: m.pricing
    }));
  } catch (error) {
    console.log(`❌ Error: ${error.message}`);
    return [];
  }
}

async function testModel(modelId) {
  try {
    const response = await fetchWithTimeout(`${BASE_URL}/chat/completions`, {
      method: 'POST',
      headers,
      body: JSON.stringify({
        model: modelId,
        messages: [{ role: 'user', content: TEST_MESSAGE }],
        max_tokens: 10
      })
    }, 30000);
    
    const data = await response.json();
    
    if (!response.ok) {
      return {
        success: false,
        status: response.status,
        error: data.error?.message || response.statusText
      };
    }
    
    return {
      success: true,
      response: data.choices?.[0]?.message?.content || 'No content'
    };
  } catch (error) {
    return {
      success: false,
      error: error.message
    };
  }
}

async function main() {
  console.log('🚀 OpenRouter Free Models Explorer\n');
  
  if (!OPENROUTER_API_KEY) {
    console.log('❌ OPENROUTER_API_KEY not found');
    return;
  }
  
  const freeModels = await getAllModels();
  
  if (freeModels.length === 0) {
    console.log('No free models found');
    return;
  }
  
  console.log('Testing free models:\n');
  console.log('| Model ID | Status | Response |');
  console.log('|----------|--------|----------|');
  
  for (const model of freeModels.slice(0, 30)) { // Test first 30
    process.stdout.write(`| ${model.id} | `);
    
    const result = await testModel(model.id);
    
    if (result.success) {
      const response = result.response.substring(0, 30).replace(/\n/g, ' ');
      console.log(`✅ OK | ${response}... |`);
    } else {
      const error = (result.error || `${result.status}`).substring(0, 40);
      console.log(`❌ ${error} | - |`);
    }
    
    // Add delay to avoid rate limiting
    await new Promise(r => setTimeout(r, 1000));
  }
  
  console.log('\n✅ Test Complete');
}

main().catch(console.error);
