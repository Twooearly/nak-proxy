<script lang="ts">
	import './layout.css';
	import favicon from '#lib/assets/favicon.svg';
	import ThemeToggle from '#lib/components/ThemeToggle.svelte';
	import type { LayoutProps } from './$types';

	let { children }: LayoutProps = $props();
</script>

<svelte:head>
	<link rel="icon" href={favicon} />
	<title>NAK Stundenplan-Abo</title>
	<meta
		name="description"
		content="Stundenplan deiner Nordakademie-Zenturie als Kalender-Abo, mit frei wählbaren Modulen."
	/>
</svelte:head>

<ThemeToggle />

{@render children()}
