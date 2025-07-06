// Ollama 모델 라이브러리와 Supabase DB의 ai_models 테이블을 동기화하는 스크립트
// PRD v1.0 - Phase 7 산출물

// 필요 라이브러리: @supabase/supabase-js, dotenv
// 실행 전 `npm install @supabase/supabase-js dotenv` 필요

import { createClient } from '@supabase/supabase-js';
import { exec } from 'child_process';
import { promisify } from 'util';
import dotenv from 'dotenv';
import path from 'path';

// .env 파일 로드 (프로젝트 루트 기준)
dotenv.config({ path: path.resolve(process.cwd(), '.env') });

const execAsync = promisify(exec);

// Supabase 클라이언트 초기화
const supabaseUrl = process.env.SUPABASE_URL;
const supabaseKey = process.env.SUPABASE_SERVICE_ROLE_KEY;

if (!supabaseUrl || !supabaseKey) {
    console.error('Error: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in .env file.');
    process.exit(1);
}

const supabase = createClient(supabaseUrl, supabaseKey);

/**
 * 로컬 Ollama 모델 목록을 조회합니다.
 * @returns {Promise<string[]>} 모델 이름 배열
 */
async function getOllamaModels() {
    try {
        const { stdout } = await execAsync('ollama list');
        const lines = stdout.trim().split('\n').slice(1); // 헤더 제외
        return lines.map(line => line.split(/\s+/)[0]); // 첫 번째 열이 모델 이름
    } catch (error) {
        console.error('Error fetching Ollama models. Is Ollama running?', error);
        return [];
    }
}

/**
 * DB에 저장된 Ollama 모델 목록을 조회합니다.
 * @returns {Promise<string[]>} 모델 이름 배열
 */
async function getDbOllamaModels() {
    const { data, error } = await supabase
        .from('ai_models')
        .select('model_name')
        .eq('provider', 'ollama');

    if (error) {
        console.error('Error fetching models from DB:', error);
        return [];
    }
    return data.map(model => model.model_name);
}

/**
 * 모델 타입 추론 (이름 기반)
 * @param {string} modelName 
 * @returns {string} 'vision' 또는 'text'
 */
function inferModelType(modelName) {
    if (modelName.includes('llava') || modelName.includes('vision')) {
        return 'vision';
    }
    return 'text';
}

/**
 * 메인 동기화 함수
 */
async function syncModels() {
    console.log('Starting Ollama model sync...');

    const [localModels, dbModels] = await Promise.all([
        getOllamaModels(),
        getDbOllamaModels(),
    ]);

    if (localModels.length === 0) {
        console.log('No local Ollama models found to sync.');
        return;
    }

    const newModels = localModels.filter(model => !dbModels.includes(model));

    if (newModels.length === 0) {
        console.log('All Ollama models are already in sync with the database.');
        return;
    }

    console.log(`Found ${newModels.length} new models to add:`, newModels.join(', '));

    const modelsToInsert = newModels.map(modelName => ({
        provider: 'ollama',
        model_name: modelName,
        model_type: inferModelType(modelName),
        config: {},
        cost_per_1k_tokens: 0, // 로컬 모델은 비용 0
        is_active: true,
    }));

    const { data, error } = await supabase.from('ai_models').insert(modelsToInsert).select();

    if (error) {
        console.error('Error inserting new models into DB:', error);
    } else {
        console.log(`Successfully added ${data.length} new models to the database.`);
    }
}

syncModels();
