<script lang="ts">
	import { onMount } from 'svelte';
	import MoonIcon from '@lucide/svelte/icons/moon';
	import SunIcon from '@lucide/svelte/icons/sun';

	import { Button } from '#lib/components/ui/button/index.js';

	// Anfangszustand hat static/theme.js schon vor dem Rendern gesetzt
	let dunkel = $state(false);

	const system = () => window.matchMedia('(prefers-color-scheme: dark)');

	function anwenden(wert: boolean) {
		dunkel = wert;
		document.documentElement.classList.toggle('dark', wert);
	}

	function umschalten() {
		const neu = !dunkel;
		anwenden(neu);
		try {
			// Entspricht die Wahl dem System, zurück auf Automatik
			if (neu === system().matches) localStorage.removeItem('theme');
			else localStorage.setItem('theme', neu ? 'dunkel' : 'hell');
		} catch {
			// localStorage gesperrt: gilt dann nur für diese Sitzung
		}
	}

	onMount(() => {
		dunkel = document.documentElement.classList.contains('dark');
		// Ohne gespeicherte Wahl der Systemeinstellung live folgen
		const mq = system();
		const onChange = (e: MediaQueryListEvent) => {
			let gespeichert: string | null = null;
			try {
				gespeichert = localStorage.getItem('theme');
			} catch {}
			if (!gespeichert) anwenden(e.matches);
		};
		mq.addEventListener('change', onChange);
		return () => mq.removeEventListener('change', onChange);
	});
</script>

<Button
	variant="ghost"
	size="icon"
	class="fixed top-3 right-3 z-50"
	onclick={umschalten}
	aria-label={dunkel ? 'Helles Design' : 'Dunkles Design'}
	title={dunkel ? 'Helles Design' : 'Dunkles Design'}
>
	{#if dunkel}
		<SunIcon class="size-5" />
	{:else}
		<MoonIcon class="size-5" />
	{/if}
</Button>
