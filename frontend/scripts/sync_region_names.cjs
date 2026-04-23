#!/usr/bin/env node

/**
 * Sync REGION_NAMES from scraper/regions_config.json → src/utils/constants.js
 *
 * Usage: node scripts/sync_region_names.js
 */

const fs = require('fs');
const path = require('path');

const CONFIG_PATH = path.resolve(__dirname, '../../scraper/regions_config.json');
const CONSTANTS_PATH = path.resolve(__dirname, '../src/utils/constants.js');

function main() {
  const config = JSON.parse(fs.readFileSync(CONFIG_PATH, 'utf8'));
  const constantsSrc = fs.readFileSync(CONSTANTS_PATH, 'utf8');

  // Build slug → name mapping from all districts/boards
  const names = {};
  for (const district of Object.values(config.districts)) {
    for (const board of district.boards) {
      names[board.slug] = board.name;
    }
  }

  // Format as JS object literal
  const entries = Object.entries(names)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([slug, name]) => `  ${slug}: '${name}'`)
    .join(',\n');

  const replacement = `export const REGION_NAMES = {\n${entries},\n};`;

  // Replace the REGION_NAMES block in constants.js
  const pattern = /export const REGION_NAMES = \{[\s\S]*?\};/;
  if (!pattern.test(constantsSrc)) {
    console.error('ERROR: Cannot find REGION_NAMES export in constants.js');
    process.exit(1);
  }

  const updated = constantsSrc.replace(pattern, replacement);
  fs.writeFileSync(CONSTANTS_PATH, updated, 'utf8');

  const count = Object.keys(names).length;
  console.log(`Synced ${count} region names from regions_config.json → constants.js`);
}

main();
