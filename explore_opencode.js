#!/usr/bin/env node
/**
 * OpenCode 模型深度探索
 */

import { config } from 'dotenv';
config();

const OPENCODE_API_KEY = process.env.OPENCODE_API_KEY;
const BASE_URL = 'https://opencode.ai/zen/v1';

const headers = {
  'Authorization': `Bearer ${OPENCODE_API_KEY}`,
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
  console.log('📋 Fetching all available models from OpenCode...\n');
  
  try {
    const response = await fetchWithTimeout(`${BASE_URL}/models`, {
      method: 'GET',
      headers
    }, 20000);
    
    if (!response.ok) {
      console.log(`❌ Failed: ${response.status} ${response.statusText}`);
      const text = await response.text();
      console.log(`   Response: ${text.substring(0, 200)}`);
      return [];
    }
    
    const data = await response.json();
    const models = data.data || [];
    
    console.log(`✓ Total models: ${models.length}\n`);
    
    return models.map(m => ({
      id: m.id,
      object: m.object,
      owned_by: m.owned_by
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
  console.log('🚀 OpenCode Models Explorer\n');
  
  if (!OPENCODE_API_KEY) {
    console.log('❌ OPENCODE_API_KEY not found');
    return;
  }
  
  const models = await getAllModels();
  
  if (models.length === 0) {
    console.log('No models found');
    return;
  }
  
  console.log('Available models:\n');
  models.forEach(m => {
    console.log(`  - ${m.id} (${m.owned_by || 'unknown'})`);
  });
  
  console.log('\nTesting first 15 models:\n');
  console.log('| Model ID | Status | Response |');
  console.log('|----------|--------|----------|');
  
  for (const model of models.slice(0, 15)) {
    process.stdout.write(`| ${model.id} | `);
    
    const result = await testModel(model.id);
    
    if (result.success) {
      const response = (result.response || '').substring(0, 30).replace(/\n/g, ' ');
      console.log(`✅ OK | ${response}... |`);
    } else {
      const error = (result.error || `${result.status}`).substring(0, 40);
      console.log(`❌ ${error} | - |`);
    }
    
    // Add delay to avoid rate limiting
    await new Promise(r => setTimeout(r, 500));
  }
  
  console.log('\n✅ Test Complete');
}

main().catch(console.error);
