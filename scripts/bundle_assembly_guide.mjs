import { build } from 'esbuild';
import { mkdir, readFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const arg = process.argv.slice(2);
if (arg.includes('--help')) {
  console.log('node scripts/bundle_assembly_guide.mjs [--output path/to/runtime.js]');
  process.exit(0);
}
if (arg.length && (arg.length !== 2 || arg[0] !== '--output')) throw new Error('Expected --output PATH');
const outfile = arg.length ? path.resolve(arg[1]) : path.join(root, 'build/assembly-guide/runtime.js');
const license = await readFile(path.join(root, 'node_modules/three/LICENSE'), 'utf8');
await mkdir(path.dirname(outfile), { recursive: true });
await build({
  absWorkingDir: root, entryPoints: ['web/assembly-guide/viewer.js'], outfile,
  bundle: true, format: 'iife', platform: 'browser', target: ['chrome120', 'firefox120', 'safari17'],
  minify: true, legalComments: 'inline',
  banner: { js: `/* Three.js / OrbitControls / STLLoader — MIT\n${license.replaceAll('*/', '* /')}\n*/` },
});
console.log('Built classic offline assembly-guide runtime.');
