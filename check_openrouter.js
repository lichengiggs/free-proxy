#!/usr/bin/env node
/**
 * 检查 OpenRouter 账号状态
 */

import { config } from 'dotenv';
config();

const OPENROUTER_API_KEY = process.env.OPENROUTER_API_KEY;
const BASE_URL = 'https://openrouter.ai/api/v1';

const headers = {
  'Authorization': `Bearer ${OPENROUTER_API_KEY}`,
  'HTTP-Referer': 'http://localhost:8765',
  'X-Title': 'OpenRouter Free Proxy'
};

async function checkCredits() {
  console.log('🔍 Checking OpenRouter account status...\n');
  
  try {
    const response = await fetch(`${BASE_URL}/credits`, {
      method: 'GET',
      headers
    });
    
    const data = await response.json();
    
    console.log('Response status:', response.status);
    console.log('Response data:', JSON.stringify(data, null, 2));
    
    if (data.total_credits !== undefined) {
      console.log(`\n💰 Total Credits: ${data.total_credits}`);
      console.log(`💳 Total Usage: ${data.total_usage || 0}`);
      console.log(`💵 Remaining: ${data.total_credits - (data.total_usage || 0)}`);
    }
  } catch (error) {
    console.log('❌ Error:', error.message);
  }
}

checkCredits();
