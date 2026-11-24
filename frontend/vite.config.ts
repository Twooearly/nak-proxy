import adapter from '@sveltejs/adapter-static';
import tailwindcss from '@tailwindcss/vite';
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

// Flask-Backend für `npm run dev` (uv run main.py)
const backend = process.env.BACKEND_URL ?? 'http://localhost:5000';

export default defineConfig({
	plugins: [
		tailwindcss(),
		sveltekit({
			compilerOptions: {
				// Force runes mode for the project, except for libraries. Can be removed in svelte 6.
				runes: ({ filename }) =>
					filename.split(/[/\\]/).includes('node_modules') ? undefined : true
			},
			// Statischer Build, wird vom Flask-Container unter / ausgeliefert
			adapter: adapter({ fallback: undefined }),
			// CSP als <meta>-Tag mit Hashes für SvelteKits Inline-Skripte
			csp: {
				mode: 'hash',
				directives: {
					'default-src': ['self'],
					'script-src': ['self'],
					'style-src': ['self', 'unsafe-inline'],
					'img-src': ['self', 'data:'],
					'font-src': ['self'],
					'connect-src': ['self'],
					'base-uri': ['self'],
					'form-action': ['self'],
					'object-src': ['none']
				}
			}
		})
	],
	server: {
		proxy: {
			'/api': backend,
			'/z': backend,
			'/stundenplan.ics': backend
		}
	}
});
